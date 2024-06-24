from subprocess import Popen
from tenacity import *
import sys, time, os, signal, psutil
from multisig_ci.sentry_wrapper import custom_sentry_trace, CustomSentryTransaction

home_directory = os.environ.get("HOME")
signal_file_path = os.path.join(home_directory, "alive.signal")
nonce_file_path = os.path.join(home_directory, "nonce.txt")
current_try_count = 0


@custom_sentry_trace
@retry(stop=stop_after_attempt(3))
@custom_sentry_trace
def run_brownie(args):
    global current_try_count

    # Kill processes to make sure we start clean
    kill_process_by_name("brownie")
    kill_process_by_cmdline("anvil")

    if os.path.exists(signal_file_path) and current_try_count == 0:
        os.remove(signal_file_path)
        print("cleaning up signal from last run")

    if os.path.exists(nonce_file_path):
        if current_try_count == 0:
            os.remove(nonce_file_path)
        else:
            print("nonce found, aborting before we trigger another tx")
            exit(1)

    p = Popen(args)

    sleep_time = 10 + min(current_try_count * 10, 60)
    print(f"waiting for alive signal, sleeping for {sleep_time} seconds")
    time.sleep(sleep_time)

    current_try_count += 1

    if not os.path.exists(signal_file_path):
        print(f"alive signal not found, killing brownie and anvil. queuing try #{current_try_count}")
        p.terminate()
        kill_process_by_cmdline("anvil")
        raise Exception()

    print("found alive signal, waiting for process to complete")
    exit_code = p.wait()
    os.remove(signal_file_path)
    exit(exit_code)

@custom_sentry_trace
def kill_process_by_cmdline(cmdline_arg_find):
    for proc in psutil.process_iter():
        for cmdline_arg in proc.cmdline():
            if cmdline_arg_find in cmdline_arg:
                pid = proc.pid
                os.kill(int(pid), signal.SIGKILL)

@custom_sentry_trace
def kill_process_by_name(proc_name):
    for proc in psutil.process_iter():
        if proc_name == proc.name():
            pid = proc.pid
            os.kill(int(pid), signal.SIGKILL)


if __name__ == "__main__":
    with CustomSentryTransaction(op="run_brownie", name="RunBrownie"):
        run_brownie(sys.argv[1:])
