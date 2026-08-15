#include <climits>

int main() {
    volatile int value = INT_MAX;
    value += 1;
    return value == INT_MIN ? 0 : 1;
}
