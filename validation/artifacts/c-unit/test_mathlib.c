#include <stdio.h>
#include "mathlib.h"

static int failures = 0;

static void check_int(const char *name, int actual, int expected) {
    if (actual != expected) {
        printf("FAIL %s expected=%d actual=%d\n", name, expected, actual);
        failures += 1;
        return;
    }
    printf("PASS %s\n", name);
}

int main(void) {
    check_int("add", add(20, 22), 42);
    check_int("multiply", multiply(6, 7), 42);
    check_int("clamp_low", clamp(-1, 0, 10), 0);
    check_int("clamp_mid", clamp(5, 0, 10), 5);
    check_int("clamp_high", clamp(11, 0, 10), 10);

    if (failures != 0) {
        printf("c unit tests failed: %d\n", failures);
        return 1;
    }

    printf("c unit tests passed: 5\n");
    return 0;
}
