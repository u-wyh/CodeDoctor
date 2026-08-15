__attribute__((noinline)) void leak_memory() {
    int *values = new int[10];
    values[0] = 42;
    asm volatile("" : : "r"(values) : "memory");
}

int main() {
    leak_memory();
    return 0;
}
