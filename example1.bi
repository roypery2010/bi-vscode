main() {
    extrn puts;
    auto i;
    i = 1;
    while (1) {
        if (argv[i] == 0) {
            return;
        }
        puts(argv[i]);
        i = i + 1;
    }
}