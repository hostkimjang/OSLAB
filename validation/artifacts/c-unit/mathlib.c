#include "mathlib.h"

int add(int left, int right) {
    return left + right;
}

int multiply(int left, int right) {
    return left * right;
}

int clamp(int value, int minimum, int maximum) {
    if (value < minimum) {
        return minimum;
    }
    if (value > maximum) {
        return maximum;
    }
    return value;
}
