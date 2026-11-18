"""AuditProxy packaged entry point; internal script dispatch precedes GUI imports."""
import multiprocessing
import sys


def main():
    multiprocessing.freeze_support()
    arguments = sys.argv[1:]
    if arguments and arguments[0] == '--run-analysis':
        if len(arguments) < 4:
            return 2
        from script_runtime import run_file
        return run_file(arguments[1], arguments[4:], arguments[2], arguments[3])
    from app import main as gui_main
    return gui_main()


if __name__ == '__main__':
    raise SystemExit(main())
