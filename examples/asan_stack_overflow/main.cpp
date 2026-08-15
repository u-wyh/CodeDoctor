int main() {
    volatile int index = 10;
    int values[10] = {};
    values[index] = 1;
    return values[index];
}
