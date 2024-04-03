#!/usr/bin/env python3
import db_utils
import subprocess
import sys
import time
import os
db = db_utils.DbUtils('root', 'qhALiqwRFNlOzwqnbXgGbKpgCZXUiSZvmAsRLlFIIMqjSQrf', 3312, '10.1.10.123', 'load')
# db = db_utils.DbUtils('root', 'qhALiqwRFNlOzwqnbXgGbKpgCZXUiSZvmAsRLlFIIMqjSQrf', 3312, 'mysql', 'load')


HOSTS = ['rosalindf', 'alice', 'tdobz', 'flor']
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
    ps_args += ' -o "|%p" -o '
    ps_args += arg_tuple[0]

COMMAND = f"ps  -e {ps_args}"

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
    'zabbix',
    'tss',
    'tcpdump',
    '_rpc',
    'usbmux',
    'avahi',
    'netdata'
]

sql = """create table if not exists processes (

        pid int,
        ppid int,
        username varchar(50) not null,
        comm varchar(100) not null,
        cputimes int not null,
        rss int not null,
        vsz bigint not null,
        thcount int not null,
        etimes int not null,
        bdstart varchar(100),
        args varchar(20000) not null,
        snapshot_time_epoch int not null,
        snapshot_datetime datetime not null,
        host varchar(20))
"""
db.execute(sql)
print("Starting up...", flush=True)
while True:
    epoch_time = int(time.time())
    os.environ['TZ'] = 'America/Los_Angeles'
    time.tzset()
    datetime_time = time.strftime('%Y-%m-%d %H:%M:%S')
    for host in HOSTS:
        print(f"Checking host {host}", flush=True)
        ssh = subprocess.Popen(["ssh", "-o", "StrictHostKeyChecking=no", f"admin@{host}", COMMAND],
                               shell=False,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
        result = ssh.stdout.readlines()
        if result == []:
            error = ssh.stderr.readlines()
            sys.stderr.write(f"error: {error}\n")

        for line in result[1:]:
            string_line = line.strip().decode("utf-8")
            sarray = string_line.split('|')

            sarray = [element.split()[1:] for element in sarray]

            sarray = sarray[1:]

            sarray = list(map(' '.join, sarray))
            
            user = sarray[2]
            process = sarray[3]
#            ppid = sarray[3]
            cputime = int(sarray[4])
            if cputime < 10:
                continue

            if user in exclude_users:
                continue
            if process in exclude_processes:
                continue

            # print(f"user: {user} {process} ", end=None)
            # for (psarg, psresult) in zip(ps_arg_tuples, sarray):
            #     print(f" {psarg[1]}:{psresult}", end=None)
            # print(f"raw: {string_line}")
            print(".", end='')

            sql = """insert into processes (pid,ppid, username,comm,cputimes,rss,vsz,thcount,etimes,bdstart,args,snapshot_time_epoch, snapshot_datetime, host) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
            args = []
            for element in sarray:
                try:
                    intelem = int(element)
                    args.append(intelem)
                except Exception:
                    args.append(element)
            args.append(epoch_time)
            args.append(datetime_time)

            args.append(host)

            cursor = db.get_cursor()
            cursor.execute(sql, args)
            db.commit()
        print(f"{host}")
    time.sleep(5 * 60)
