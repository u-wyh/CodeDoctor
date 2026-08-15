int main() {
    volatile unsigned int shift = 32;
    volatile unsigned int result = 1U << shift;
    return static_cast<int>(result);
}
