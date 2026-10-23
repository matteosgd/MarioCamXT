/* MarioCam XT 0.1 - experimental extension for the exact BXT build below.
 * MIT licensed; see LICENSE-MarioCam.txt.
 * Build-specific glue is isolated at the bottom of this file.
 * No Windows imports, background threads, key interception, or game-state hooks.
 */
typedef unsigned int u32;
typedef unsigned char u8;

typedef struct { const char *p; int n; } Token;
typedef struct { const char *p, *end; } Reader;

static int space(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }
static int equal(Token t, const char *s) {
    int i = 0;
    while (i < t.n && s[i] && t.p[i] == s[i]) ++i;
    return i == t.n && !s[i];
}
static int next_token(Reader *r, Token *t) {
    const char *p = r->p;
    for (;;) {
        while (p < r->end && space(*p)) ++p;
        if (r->end - p >= 2 && p[0] == '/' && p[1] == '/') {
            while (p < r->end && *p != '\n') ++p;
        } else break;
    }
    if (p >= r->end || !*p) { r->p = p; return 0; }
    if (*p == '"') {
        t->p = ++p;
        while (p < r->end && *p && *p != '"') ++p;
        if (p >= r->end || *p != '"') return -1;
        t->n = (int)(p - t->p); r->p = p + 1; return 1;
    }
    t->p = p;
    if (*p == '{' || *p == '}') ++p;
    else while (p < r->end && *p && !space(*p) && *p != '{' && *p != '}') ++p;
    t->n = (int)(p - t->p); r->p = p; return 1;
}
static int finite_angle(float f) {
    union { float f; u32 u; } x;
    x.f = f;
    return (x.u & 0x7f800000u) != 0x7f800000u && f >= -1000000.0f && f <= 1000000.0f;
}
/* Bounded decimal parser. BSP angles are ordinary decimal numbers. */
static int decimal(const char **at, const char *end, float *out) {
    const char *p = *at;
    int sign = 1, digits = 0, exponent = 0, esign = 1;
    double v = 0.0, scale = 0.1;
    while (p < end && space(*p)) ++p;
    if (p < end && (*p == '-' || *p == '+')) { if (*p == '-') sign = -1; ++p; }
    while (p < end && *p >= '0' && *p <= '9') {
        if (++digits > 32) return 0;
        v = v * 10.0 + (*p++ - '0');
    }
    if (p < end && *p == '.') {
        ++p;
        while (p < end && *p >= '0' && *p <= '9') {
            if (++digits > 32) return 0;
            v += (*p++ - '0') * scale; scale *= 0.1;
        }
    }
    if (!digits) return 0;
    if (p < end && (*p == 'e' || *p == 'E')) {
        ++p;
        if (p < end && (*p == '-' || *p == '+')) { if (*p == '-') esign = -1; ++p; }
        if (p == end || *p < '0' || *p > '9') return 0;
        while (p < end && *p >= '0' && *p <= '9') {
            exponent = exponent * 10 + (*p++ - '0');
            if (exponent > 30) return 0;
        }
        while (exponent-- > 0) v = esign > 0 ? v * 10.0 : v * 0.1;
    }
    *out = (float)(sign * v);
    if (!finite_angle(*out)) return 0;
    *at = p; return 1;
}
static int vector(Token t, float *v, int count) {
    const char *p = t.p, *end = t.p + t.n;
    int i;
    for (i = 0; i < count; ++i) if (!decimal(&p, end, v + i)) return 0;
    while (p < end && space(*p)) ++p;
    return p == end;
}
static u32 little32(const u8 *p) {
    return (u32)p[0] | ((u32)p[1] << 8) | ((u32)p[2] << 16) | ((u32)p[3] << 24);
}

/* Read the first info_player_start, as standard singleplayer spawn selection does.
 * This reads only the entity lump; nothing in the BSP is written or executed.
 */
int mc_find_spawn(const u8 *bsp, u32 size, float *out) {
    u32 offset, length;
    Reader r;
    Token t, key, value;
    if (!bsp || size < 124 || little32(bsp) != 30) return 0;
    offset = little32(bsp + 4); length = little32(bsp + 8);
    if (offset < 124 || offset > size || length > size - offset || !length) return 0;
    r.p = (const char *)bsp + offset; r.end = r.p + length;
    while (next_token(&r, &t) == 1) {
        int is_start = 0, valid = 1, closed = 0;
        float a[3] = {0.0f, 0.0f, 0.0f};
        if (!equal(t, "{")) return 0;
        while (next_token(&r, &key) == 1) {
            if (equal(key, "}")) { closed = 1; break; }
            if (equal(key, "{") || next_token(&r, &value) != 1 || equal(value, "}") || equal(value, "{")) return 0;
            if (equal(key, "classname")) is_start = equal(value, "info_player_start");
            else if (equal(key, "angles")) valid = vector(value, a, 3);
            else if (equal(key, "angle")) {
                float yaw = 0.0f;
                valid = vector(value, &yaw, 1);
                a[0] = 0.0f; a[1] = yaw; a[2] = 0.0f;
                if (yaw == -1.0f) { a[0] = -90.0f; a[1] = 0.0f; }
                if (yaw == -2.0f) { a[0] = 90.0f; a[1] = 0.0f; }
            }
        }
        if (!closed) return 0;
        if (is_start) {
            if (!valid) return 0;
            out[0] = a[0]; out[1] = a[1]; out[2] = a[2]; return 1;
        }
    }
    return 0;
}

int mc_turn_angles(float *a, float step) {
    float yaw;
    int turns;
    if (!finite_angle(a[0]) || !finite_angle(a[1]) || !finite_angle(a[2])) return 0;
    yaw = a[1] + step;
    turns = (int)(yaw / 360.0f);
    yaw -= (float)turns * 360.0f;
    if (yaw < 0.0f) yaw += 360.0f;
    if (yaw >= 360.0f) yaw -= 360.0f;
    a[1] = yaw;
    return 1;
}

#ifndef MC_CORE_ONLY
/* All RVAs below are specific to the user's unmodified nov-11-2024 HL DLL:
 * SHA256 34618c2273b38b1f4690c1feef8aa00f32c7f5bf3765f7f0bbb7a303feb60840
 * Source cbc496b1ba7f6c242a961c33f16d3b5741371dd6.
 * The packer verifies the full hash and the intercepted CALL before modifying it.
 * _ImageBase is a linker symbol with a PE HIGHLOW relocation, never a fixed
 * runtime address. Each existing BXT pointer is resolved again on every command.
 */
extern const char _ImageBase;
typedef void (*Command)(void);
typedef void (__attribute__((fastcall)) *AddCommand)(const char *, Command);
typedef void (*AnglesFn)(float *);
typedef void (*PrintFn)(const char *);
typedef void (*PrintfFn)(const char *, ...);
typedef const char *(*StringFn)(void);
typedef u8 *(*LoadFn)(char *, int, int *);
typedef void (*FreeFn)(void *);
typedef int (*IntFn)(void);

static u32 base(void) { return (u32)&_ImageBase; }
static void **engine(void) { return *(void ***)(base() + 0x13d91cc0u); }
static void say(void **e, const char *s) { if (e && e[30]) ((PrintFn)e[30])(s); }
static int ready(void **e) {
    const char *map;
    if (!e || !e[34] || !e[35] || !e[74] || !e[36]) return 0;
    map = ((StringFn)e[74])();
    if (!map || !*map) { say(e, "MarioCam XT: load a singleplayer map first.\n"); return 0; }
    if (((IntFn)e[36])() != 1) { say(e, "MarioCam XT: these commands are for singleplayer.\n"); return 0; }
    return 1;
}
static void turn(float step) {
    void **e = engine();
    float a[3];
    if (!ready(e)) return;
    ((AnglesFn)e[34])(a);
    if (mc_turn_angles(a, step)) ((AnglesFn)e[35])(a);
    else say(e, "MarioCam XT: invalid view angles; no change made.\n");
}
void mc_left(void) { turn(45.0f); }
void mc_right(void) { turn(-45.0f); }

/* The reference is always read from c1a0, regardless of the current map or save.
 * Cache is keyed by engine table and game directory so a game switch invalidates it.
 */
static int reference_ready;
static float reference[3];
static void **reference_engine;
static char reference_dir[260];
static int same_dir(const char *s) {
    unsigned i;
    if (!s) return 0;
    for (i = 0; i < sizeof(reference_dir); ++i) {
        if (reference_dir[i] != s[i]) return 0;
        if (!s[i]) return 1;
    }
    return 0;
}
static int get_reference(void **e) {
    const char *dir;
    u8 *file;
    int size = 0, ok;
    unsigned i;
    float a[3];
    if (!e[79] || !e[81] || !e[71]) return 0;
    dir = ((StringFn)e[71])();
    if (reference_ready && reference_engine == e && same_dir(dir)) return 1;
    reference_ready = 0;
    file = ((LoadFn)e[79])("maps/c1a0.bsp", 5, &size);
    if (!file) { say(e, "MarioCam XT: maps/c1a0.bsp could not be read; view unchanged.\n"); return 0; }
    ok = size > 0 && mc_find_spawn(file, (u32)size, a);
    ((FreeFn)e[81])(file);
    if (!ok) { say(e, "MarioCam XT: no valid c1a0 player-start angles; view unchanged.\n"); return 0; }
    reference[0] = a[0]; reference[1] = a[1]; reference[2] = a[2];
    reference_engine = e;
    for (i = 0; i + 1 < sizeof(reference_dir) && dir && dir[i]; ++i) reference_dir[i] = dir[i];
    reference_dir[i] = 0;
    reference_ready = 1;
    return 1;
}
void mc_reset(void) {
    void **e = engine();
    float a[3];
    if (!ready(e) || !get_reference(e)) return;
    a[0] = reference[0]; a[1] = reference[1]; a[2] = reference[2];
    ((AnglesFn)e[35])(a);
}
void mc_info(void) {
    void **e = engine();
    say(e, "MarioCam XT 0.1 EXPERIMENTAL / BXT nov-11-2024\nCommands: mariocam_left, mariocam_right, mariocam_reset\nLeft/right: relative 45 degrees. Reset: c1a0 player-start pitch/yaw/roll.\n");
    if (ready(e) && get_reference(e) && e[40])
        ((PrintfFn)e[40])("MarioCam XT reset angles: %.6f %.6f %.6f\n", (double)reference[0], (double)reference[1], (double)reference[2]);
}
void __attribute__((fastcall)) mc_register(const char *name, Command original) {
    AddCommand add = (AddCommand)(base() + 0x000c0de0u);
    /* Register the original bxt_set_angles callback exactly as before. */
    add(name, original);
    add("mariocam_left", mc_left);
    add("mariocam_right", mc_right);
    add("mariocam_reset", mc_reset);
    add("mariocam_info", mc_info);
}
#endif
