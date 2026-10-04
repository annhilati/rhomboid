import sys

def apply_resource_limits(max_mb: int, max_cpu: int, max_files: int):
    # Pterodactyl enforces limits via Docker cgroups, so we don't need setrlimit.
    # Furthermore, using setrlimit inside a container can cause hangs or crashes.
    pass