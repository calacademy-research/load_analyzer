#!/usr/bin/env python3
import mysql.connector
import subprocess
import signal
import sys
import time
import os


def ssh_with_timeout(cmd, timeout_secs=30):
    """Run SSH command using shell timeout and temp files to avoid pipe hangs."""
    import tempfile
    import shlex
    stdout_file = tempfile.NamedTemporaryFile(mode='w+', suffix='.out', delete=False)
    stderr_file = tempfile.NamedTemporaryFile(mode='w+', suffix='.err', delete=False)
    stdout_path = stdout_file.name
    stderr_path = stderr_file.name
    stdout_file.close()
    stderr_file.close()
    try:
        shell_cmd = f"timeout -k 5 {timeout_secs} " + " ".join(shlex.quote(c) for c in cmd) + f" > {stdout_path} 2> {stderr_path}"
        print(f"  Running: {shell_cmd[:120]}...", flush=True)
        rc = os.system(shell_cmd)
        print(f"  os.system returned: {rc}", flush=True)
        rc = rc >> 8  # get actual exit code
        with open(stdout_path) as f:
            stdout = f.read()
        with open(stderr_path) as f:
            stderr = f.read()
        if rc == 124:  # timeout exit code
            return None, f"Timed out after {timeout_secs}s", -1
        return stdout, stderr, rc
    finally:
        try:
            os.unlink(stdout_path)
        except OSError:
            pass
        try:
            os.unlink(stderr_path)
        except OSError:
            pass

class DbUtils:
    def __init__(self, user, password, port, host, database):
        self.conn = mysql.connector.connect(
            user=user,
            password=password,
            host=host,
            port=port,
            database=database,
            autocommit=True,
        )

    def get_cursor(self):
        return self.conn.cursor()

    def execute(self, query, params=None):
        cur = self.conn.cursor()
        cur.execute(query, params)
        cur.close()

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

db = DbUtils(
    'root',
    'qhALiqwRFNlOzwqnbXgGbKpgCZXUiSZvmAsRLlFIIMqjSQrf',
    3312,
    '10.4.90.123',
    'load',
)

HOSTS = ['rosalindf', 'alice', 'tdobz', 'flor', 'ibss-spark-1']
GPU_HOSTS = ['alice', 'ibss-spark-1']

ps_arg_tuples = [
    ('pid', 'process ID'),
    ('ppid', 'parent process ID'),
    ('user:30', 'username'),
    ('comm', 'command name'),
    ('cputimes', 'CPU time seconds'),
    ('rss', 'physical memory in K'),
    ('vsz', 'virtual memory in K'),
    ('thcount', 'Thread count'),
    ('etimes', 'elapsed time in seconds'),
    ('bsdstart', 'start time'),
    ('args', 'full command'),

]

ps_args = ''
for arg_tuple in ps_arg_tuples:
    ps_args += ' -o "|%p " -o '
    ps_args += arg_tuple[0]

COMMAND = f"ps  -e {ps_args}"
GPU_COMMAND = "nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits && echo '---GPU_PROCS---' && nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv,noheader,nounits 2>/dev/null && echo '---PS_DATA---' && ps -eo pid,user --no-headers"

exclude_processes = ['bash', 'sshd', '(sd-pam)', 'screen', 'systemd']

exclude_users = [
    'root',
    'daemon',
    'bin',
    'sys',
    'sync',
    'games',
    'man',
    'lp',
    'mail',
    'news',
    'uucp',
    'proxy',
    'www-data',
    'backup',
    'list',
    'irc',
    'gnats',
    'nobody',
    'systemd-network',
    'systemd-resolve',
    'syslog',
    'messagebus',
    '_apt',
    'lxd',
    'uuidd',
    'dnsmasq',
    'landscape',
    'pollinate',
    'sshd',
    'sssd',
    'statd',
    'ntp',
    'nagios',
    'scan',
    'sophosav',
    'sophos-spl-av',
    'sophos-spl-local',
    'sophos-spl-updatescheduler',
    'sophos-spl-user',
    'zabbix',
    'tss',
    'tcpdump',
    '_rpc',
    'usbmux',
    'avahi',
    'netdata',
    'gdm',
    'gnome-remote-desktop',
    'ntpsec',
    'nx',
    'polkitd',
    'rstudio-server',
    'rtkit',
    'munge',
]

sql = """create table if not exists processes (

        pid int,
        ppid int,
        username varchar(50) not null,
        comm varchar(100) not null,
        cputimes int not null,
        rss int not null,
        pss int not null default 0,
        vsz bigint not null,
        thcount int not null,
        etimes int not null,
        bdstart varchar(100),
        args TEXT not null,
        snapshot_time_epoch int not null,
        snapshot_datetime datetime not null,
        host varchar(20))
"""
db.execute(sql)

# Add pss column if it doesn't exist (for existing tables)
try:
    db.execute("ALTER TABLE processes ADD COLUMN pss int NOT NULL DEFAULT 0 AFTER rss")
    print("Added pss column to processes")
except Exception:
    pass  # Column already exists

gpu_sql = """create table if not exists gpu_stats (
        host varchar(20) not null,
        gpu_index int not null,
        gpu_name varchar(100),
        utilization_pct float,
        memory_used_mb float,
        memory_total_mb float,
        gpu_processes text,
        snapshot_time_epoch int not null,
        snapshot_datetime datetime not null,
        INDEX idx_gpu_snapshot_datetime (snapshot_datetime),
        INDEX idx_gpu_host (host))
"""
db.execute(gpu_sql)

# Add gpu_processes column if it doesn't exist (for existing tables)
try:
    db.execute("ALTER TABLE gpu_stats ADD COLUMN gpu_processes text AFTER memory_total_mb")
    print("Added gpu_processes column to gpu_stats")
except Exception:
    pass  # Column already exists

print("Starting up...", flush=True)
while True:
    epoch_time = int(time.time())
    os.environ['TZ'] = 'America/Los_Angeles'
    time.tzset()
    datetime_time = time.strftime('%Y-%m-%d %H:%M:%S')
    for host in HOSTS:
        print(f"Checking host {host}", flush=True)
        ssh = subprocess.Popen(["ssh", "-i", "/root/.ssh/id_rsa", "-o", "StrictHostKeyChecking=no", f"admin@{host}", COMMAND],
                               shell=False,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
        cmd = ["ssh", "-i", "/root/.ssh/id_rsa", "-o", "StrictHostKeyChecking=no", f"admin@{host}", COMMAND]
        print(f"command: {' '.join(cmd)}")
        result = ssh.stdout.readlines()
        ssh.wait()  # reap child process to prevent zombies
        if result == []:
            error = ssh.stderr.readlines()
            sys.stderr.write(f"error: {error}\n")

        # First pass: parse ps output and collect filtered PIDs
        filtered_rows = []
        for line in result[1:]:
            string_line = line.strip().decode("utf-8")
            sarray = string_line.split('|')

            sarray = [element.split()[1:] for element in sarray]

            sarray = sarray[1:]

            sarray = list(map(' '.join, sarray))

            user = sarray[2]
            process = sarray[3]
            cputime = int(sarray[4])
            if cputime < 10:
                continue

            if user in exclude_users:
                continue
            if process in exclude_processes:
                continue

            filtered_rows.append(sarray)

        # Collect PSS for all filtered PIDs in a single SSH call
        pss_map = {}
        if filtered_rows:
            pids = [row[0] for row in filtered_rows]
            pids_str = ' '.join(pids)
            pss_cmd = f"for pid in {pids_str}; do pss=$(awk '/^Pss:/{{s+=$2}} END{{print s+0}}' /proc/$pid/smaps_rollup 2>/dev/null); echo \"$pid|$pss\"; done"
            pss_ssh = subprocess.Popen(
                ["ssh", "-i", "/root/.ssh/id_rsa", "-o", "StrictHostKeyChecking=no",
                 f"admin@{host}", f"sudo sh -c '{pss_cmd}'"],
                shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            pss_result = pss_ssh.stdout.readlines()
            pss_ssh.wait()
            for pss_line in pss_result:
                parts = pss_line.strip().decode("utf-8").split('|')
                if len(parts) == 2:
                    try:
                        pss_map[parts[0]] = int(float(parts[1]))
                    except (ValueError, TypeError):
                        pass

        # Insert rows with PSS data
        for sarray in filtered_rows:
            pid_str = sarray[0]
            pss_kb = pss_map.get(pid_str, 0)

            print(".", end='')

            sql = """insert into processes (pid,ppid, username,comm,cputimes,rss,pss,vsz,thcount,etimes,bdstart,args,snapshot_time_epoch, snapshot_datetime, host) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
            args = []
            for element in sarray:
                try:
                    intelem = int(element)
                    args.append(intelem)
                except Exception:
                    args.append(element)
            # Insert PSS after rss (index 5 in the values)
            args.insert(5, pss_kb)
            args.append(epoch_time)
            args.append(datetime_time)

            args.append(host)

            cursor = db.get_cursor()
            cursor.execute(sql, args)
            db.commit()
        print(f"{host}")

    # Collect GPU stats from GPU-equipped hosts
    for host in GPU_HOSTS:
        print(f"Checking GPU on {host}", flush=True)
        try:
            ssh_cmd = ["ssh", "-i", "/root/.ssh/id_rsa", "-o", "StrictHostKeyChecking=no",
                       "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=5",
                       "-o", "ServerAliveCountMax=3", f"admin@{host}", GPU_COMMAND]
            stdout, stderr, rc = ssh_with_timeout(ssh_cmd, timeout_secs=30)
            if stdout is None:
                sys.stderr.write(f"GPU collection timed out for {host}\n")
                continue
            output = stdout.strip()
            if not output:
                if stderr:
                    sys.stderr.write(f"GPU error on {host}: {stderr}\n")
                continue

            # Parse combined output: GPU stats, then process info, then ps data
            gpu_lines = []
            gpu_proc_lines = []
            ps_lines = []
            section = 'gpu'
            for line in output.split('\n'):
                if line.strip() == '---GPU_PROCS---':
                    section = 'procs'
                    continue
                elif line.strip() == '---PS_DATA---':
                    section = 'ps'
                    continue
                if section == 'gpu':
                    gpu_lines.append(line)
                elif section == 'procs':
                    gpu_proc_lines.append(line)
                elif section == 'ps':
                    ps_lines.append(line)

            # Build pid->user map
            pid_user = {}
            for ps_line in ps_lines:
                ps_fields = ps_line.strip().split()
                if len(ps_fields) >= 2:
                    pid_user[ps_fields[0]] = ps_fields[1]

            # Parse GPU processes
            procs = []
            for gp_line in gpu_proc_lines:
                gp_fields = [f.strip() for f in gp_line.split(",")]
                if len(gp_fields) >= 3:
                    pid = gp_fields[0]
                    proc_name = gp_fields[1]
                    gpu_mem = gp_fields[2]
                    user = pid_user.get(pid, "?")
                    procs.append(f"{user}:{proc_name}({gpu_mem}MB)")
            gpu_processes_str = ", ".join(procs) if procs else ""

            for line in gpu_lines:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) < 5:
                    continue

                gpu_index = int(parts[0])
                gpu_name = parts[1]
                try:
                    utilization = float(parts[2])
                except (ValueError, TypeError):
                    utilization = None
                try:
                    mem_used = float(parts[3])
                except (ValueError, TypeError):
                    mem_used = None
                try:
                    mem_total = float(parts[4])
                except (ValueError, TypeError):
                    mem_total = None

                gpu_insert_sql = """insert into gpu_stats
                    (host, gpu_index, gpu_name, utilization_pct, memory_used_mb, memory_total_mb,
                     gpu_processes, snapshot_time_epoch, snapshot_datetime)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                cursor = db.get_cursor()
                cursor.execute(gpu_insert_sql, (
                    host, gpu_index, gpu_name, utilization, mem_used, mem_total,
                    gpu_processes_str or None, epoch_time, datetime_time))
                db.commit()
                print(f"GPU {gpu_index} on {host}: {utilization}% util, {mem_used}/{mem_total} MB, procs: {gpu_processes_str}")
        except Exception as e:
            sys.stderr.write(f"GPU collection failed for {host}: {e}\n")

    time.sleep(5 * 60)
