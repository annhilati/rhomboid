import sys

def apply_resource_limits(max_mb: int, max_cpu: int, max_files: int):
    try:
        import resource
        bytes_limit = max_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (bytes_limit, bytes_limit))
        resource.setrlimit(resource.RLIMIT_CPU, (max_cpu, max_cpu))
        resource.setrlimit(resource.RLIMIT_NOFILE, (max_files, max_files))
    except ImportError:
        # Windows doesn't support resource module natively.
        pass