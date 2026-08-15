__attribute__((noinline)) void release(int *pointer) {
    delete pointer;
}

int main() {
    int *pointer = new int(1);
    release(pointer);
    release(pointer);
    return 0;
}
