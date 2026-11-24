#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define VERSION "1.0.0"
#define OS_FAMILIES 20
#define TOTAL_RELEASES 100

/* Kody kolorow ANSI */
#define C_RESET  "\033[0m"
#define C_BLUE   "\033[1;34m"
#define C_CYAN   "\033[1;36m"
#define C_GREEN  "\033[1;32m"
#define C_YELLOW "\033[1;33m"
#define C_BOLD   "\033[1m"

void print_fetch(void) {
    printf("\n");
    printf(C_BLUE "       .---.        " C_BOLD "METAISO.net CLI" C_RESET " v%s\n", VERSION);
    printf(C_BLUE "      /     \\       " C_RESET "-------------------------\n");
    printf(C_BLUE "     |  " C_CYAN "(O)" C_BLUE "  |      " C_CYAN "Archive:" C_RESET "  https://github.io\n");
    printf(C_BLUE "      \\     /       " C_CYAN "Families:" C_RESET " %d operating system families\n", OS_FAMILIES);
    printf(C_BLUE "       '---'        " C_CYAN "Releases:" C_RESET " %d verified ISO images\n", TOTAL_RELEASES);
    printf(C_BLUE "    .---------.     " C_CYAN "Security:" C_RESET " SHA-256 Checksum Verified\n");
    printf(C_BLUE "   /  METAISO  \\    " C_CYAN "Arch:" C_RESET "     x86-64, ARM64, 32-bit\n");
    printf(C_BLUE "  '-------------'   " C_CYAN "License:" C_RESET "  Apache-2.0 (Non-profit)\n");
    printf("\n");
}

void print_list(void) {
    const char *families[] = {
        "Windows", "Ubuntu", "Debian", "Fedora", "Kali OS",
        "Arch Linux", "Gentoo", "Alpine Linux", "BSD (FreeBSD/OpenBSD)",
        "Zorin OS", "Pop!_OS", "Manjaro", "MacroMag OS", "Nobara",
        "Talis OS", "Rocky Linux", "CentOS", "Oracle Linux",
        "Red Hat (RHEL)", "SUSE / Solaris / macOS / ReactOS"
    };
    int count = sizeof(families) / sizeof(families[0]);

    printf(C_BOLD "\nSupported OS Families (%d):\n" C_RESET, count);
    for (int i = 0; i < count; i++) {
        printf("  " C_GREEN "•" C_RESET " %s\n", families[i]);
    }
    printf("\nDownload direct ISOs at: " C_CYAN "https://github.io\n\n" C_RESET);
}

void verify_sha256(const char *filepath, const char *expected_hash) {
    char cmd[1024];
    char output[256];

    snprintf(cmd, sizeof(cmd), "sha256sum \"%s\" 2>/dev/null || shasum -a 256 \"%s\" 2>/dev/null", filepath, filepath);
    FILE *pipe = popen(cmd, "r");
    if (!pipe) {
        fprintf(stderr, "Error: Could not execute system SHA-256 utility.\n");
        return;
    }

    if (fgets(output, sizeof(output), pipe) != NULL) {
        char calculated[65] = {0};
        strncpy(calculated, output, 64);

        printf("Calculated: %s\n", calculated);
        printf("Expected:   %s\n", expected_hash);

        if (strncmp(calculated, expected_hash, 64) == 0) {
            printf(C_GREEN "[OK] SHA-256 checksum matches! ISO image is authentic.\n" C_RESET);
        } else {
            printf(C_YELLOW "[WARNING] Checksum mismatch! Do not use this ISO file.\n" C_RESET);
        }
    } else {
        fprintf(stderr, "Error: File not found or sha256sum not installed.\n");
    }
    pclose(pipe);
}

void print_help(const char *prog) {
    printf("Usage: %s [OPTION]\n", prog);
    printf("Options:\n");
    printf("  (no args)               Display METAISO system summary (fastfetch style)\n");
    printf("  -l, --list              List all supported OS families\n");
    printf("  -v, --verify FILE HASH  Verify SHA-256 checksum of a downloaded .iso\n");
    printf("  -h, --help              Show this help message\n");
}

int main(int argc, char *argv[]) {
    if (argc == 1) {
        print_fetch();
        return 0;
    }

    if (strcmp(argv[1], "-l") == 0 || strcmp(argv[1], "--list") == 0) {
        print_list();
    } else if ((strcmp(argv[1], "-v") == 0 || strcmp(argv[1], "--verify") == 0) && argc == 4) {
        verify_sha256(argv[2], argv[3]);
    } else {
        print_help(argv[0]);
    }

    return 0;
}
