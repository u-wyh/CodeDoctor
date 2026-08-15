int main() {
    int *pointer = new int(7);
    delete pointer;
    volatile int result = *pointer;
    return result;
}
