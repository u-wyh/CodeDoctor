int main() {
    volatile int zero = 0;
    volatile int result = 42 / zero;
    return result;
}
