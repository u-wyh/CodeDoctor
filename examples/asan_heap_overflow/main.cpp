int main() {
    int *values = new int[10]{};
    volatile int index = 10;
    values[index] = 1;
    int result = values[index];
    delete[] values;
    return result == 1 ? 0 : 1;
}
