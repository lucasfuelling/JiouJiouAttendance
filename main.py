#!/usr/bin/env python
from datetime import datetime
from datetime import timedelta
import time
import csv
from threading import *
import requests
import mariadb
import os

thread_running = True
token = "nhT4TzFE5b0NO3YMiMUlXexfqJrK23CAyyHuQyDEdP3"
max_overhours = 46

def clear():
    print("\033c")


def line_notify_message(line_token, msg):
    headers = {
        "Authorization": "Bearer " + line_token,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {'message': msg}
    r = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
    return r.status_code


def connect_to_mariadb():
    conn = mariadb.connect(
        user="jiou99",
        password="jiou99",
        host="localhost",
        port=3306,
        database="attendance"
    )
    return conn


def user_exists(conn, mychip):
    cur = conn.cursor()
    sql = "SELECT userid FROM users WHERE chipno=?"
    par = (mychip,)
    cur.execute(sql, par)
    if cur.fetchone():
        return bool(True)
    else:
        return bool(False)


def user_clocked(conn, mychip):
    cur = conn.cursor()
    todays_date = datetime.now().strftime("%Y-%m-%d")
    sql = "SELECT userid FROM attendance INNER JOIN users USING(userid) WHERE clockout_B is NULL AND chipno=? AND " \
          "clockday =? "
    par = (mychip, todays_date)
    cur.execute(sql, par)
    if cur.fetchone():
        return bool(True)
    else:
        return bool(False)


def short_clock_in_time(conn, mychip):
    cur = conn.cursor()
    todays_date = datetime.now().strftime("%Y-%m-%d")
    one_minutes_ago = datetime.now() - timedelta(minutes=1)
    sql = "SELECT clockin_B FROM attendance INNER JOIN users USING(userid) WHERE (clockout_B >= ? OR clockin_B >= ?) AND " \
          "chipno=? AND clockday =? "
    par = (one_minutes_ago.strftime("%H:%M"), one_minutes_ago.strftime("%H:%M"), mychip, todays_date)
    cur.execute(sql, par)
    if cur.fetchone():
        return bool(True)
    else:
        return bool(False)


def attendance_come(conn, mychip):
    if not short_clock_in_time(conn, mychip):
        global token
        par = (mychip,)
        come_time = datetime.now().strftime("%H:%M")
        todays_date = datetime.now().strftime("%Y-%m-%d")
        cur = conn.cursor()
        sql = "SELECT userid, name FROM users WHERE chipno = ?"
        cur.execute(sql, par)
        userid, name = cur.fetchone()

        sql = "select sum(overhours) from attendance where month(clockday) = month(curdate()) and userid = ?"
        par = (userid,)
        cur.execute(sql, par)
        overhours, = cur.fetchone()
        if overhours is None:
            overhours = 0
        # clockin_A not on saturday if overhours > max_overhours
        if overhours > max_overhours and datetime.today().weekday() == 5:
            sql = "INSERT INTO attendance(userid, username, clockday, clockin_A, clockin_B)" \
                  "VALUES (?,?,?,?,?)"
            par = (userid, name, todays_date, None, come_time)
        else:
            sql = "INSERT INTO attendance(userid, username, clockday, clockin_A, clockin_B)" \
                  "VALUES (?,?,?,?,?)"
            par = (userid, name, todays_date, come_time, come_time)
        cur.execute(sql, par)
        conn.commit()
        print(name + " " + come_time + " " + "上班")
        today_8am = datetime.now().replace(hour=8, minute=0)
        if today_8am < datetime.now():
            msg = name + " " + come_time + "上班"
            line_notify_message(token, msg)
    else:
        print("已打卡了")


def attendance_go(conn, mychip):
    if not short_clock_in_time(conn, mychip):
        go_time_17 = datetime.now().replace(hour=17, minute=0).strftime("%H:%M")
        go_time = datetime.now().strftime("%H:%M")
        todays_date = datetime.now().strftime("%Y-%m-%d")

        # get userid and username from chip number
        cur = conn.cursor()
        sql = "SELECT userid, name FROM users WHERE chipno = ?"
        par = (mychip,)
        cur.execute(sql, par)
        userid, name = cur.fetchone()
        overhours = get_overhours(cur, userid)

        sql = "UPDATE attendance SET clockout_A = ?, clockout_B = ? WHERE userid = ? AND clockout_A is NULL AND clockday = ?"
        # clockout_A = 17:00 if overhours are too much
        if overhours > max_overhours:
            par = (go_time_17, go_time, userid, todays_date)
        # clockout_A = None on saturdays because no clockin
        if overhours > max_overhours and datetime.today().weekday() == 5:
            par = (None, go_time, userid, todays_date)
        else:
            par = (go_time, go_time, userid, todays_date)
        cur.execute(sql, par)
        conn.commit()
        print(name + " " + go_time + " " + "下班")
        calc_overhours(cur, conn, mychip)
    else:
        print("已打卡了")


def calc_overhours(cur, conn, mychip):
    sql = "SELECT userid, name FROM users WHERE chipno = ?"
    par = (mychip,)
    cur.execute(sql, par)
    userid, name = cur.fetchone()

    sql = "select clockin_B, clockout_B from attendance where userid = ? and clockday = curdate()"
    par = (userid,)
    cur.execute(sql, par)
    clockin, clockout = cur.fetchone()
    lunch_time = timedelta(hours=1)
    dinner_time = timedelta(minutes=30)
    if clockin <= timedelta(hours=12) and clockout >= timedelta(hours=17, minutes=30):
        worked_time = clockout - clockin - lunch_time - dinner_time
    if clockin >= timedelta(hours=13) and clockout >= timedelta(hours=17, minutes=30):
        worked_time = clockout - clockin - dinner_time
    if clockin >= timedelta(hours=12) and clockout >= timedelta(hours=13) and clockout <= timedelta(hours=17, minutes=30):
        worked_time = clockout - clockin - lunch_time
    else:
        worked_time = clockout - clockin

    if worked_time >= timedelta(hours=8):
        overhours = worked_time - timedelta(hours=8)
    else:
        overhours = timedelta(hours=0)
    sql = "UPDATE attendance SET overhours = ? WHERE userid = ? and clockday = curdate() and overhours is null"
    par = (overhours, userid)
    cur.execute(sql, par)
    conn.commit()


def get_overhours(cur, userid):
    sql = "select sum(overhours) from attendance where month(clockday) = month(curdate()) and userid = ?"
    par = (userid,)
    cur.execute(sql, par)
    overhours, = cur.fetchone()
    if overhours is None:
        return 0
    else:
        return overhours


def export_data(conn):
    month = datetime.now().month
    year = datetime.now().year - 1911
    str_year = str(year)
    str_month = str(month).zfill(2)
    cur = conn.cursor()
    csv_writer = csv.writer(open("打卡-" + str_year + "-" + str_month + ".csv", "w", encoding='utf-8-sig', newline=''))
    sql = "SELECT username, clockday, DATE_FORMAT(clockin_A,'%k:%i') as 'clockin_A', DATE_FORMAT(clockout_A,'%k:%i') as " \
          "'clockout_A' FROM attendance where month(clockday) = month(curdate()) ORDER BY userid ASC, clockday ASC "
    cur.execute(sql)
    rows = cur.fetchall()
    csv_writer.writerow(["Name", "Date", "Come", "Go"])
    csv_writer.writerows(rows)


def reader():
    while True:
        global thread_running
        mychip = input()
        try:
            conn = connect_to_mariadb()
            event.set()
            clear()
            if user_exists(conn, mychip) or mychip == "0002245328":
                if mychip != "0002245328":
                    if user_clocked(conn, mychip):
                        attendance_go(conn, mychip)
                        export_data(conn)
                    else:
                        attendance_come(conn, mychip)
                else:
                    shutdown()
            else:
                print("沒有找到用戶" + str(mychip))
            time.sleep(1.8)
            event.clear()
            conn.close()
        except mariadb.Error as e:
            print(e)
            event.set()
            time.sleep(1.5)
            event.clear()


def shutdown():
    os.system("sudo shutdown -h now")


# shows time
def background_thread():
    while True:
        while not event.isSet():
            now = datetime.now()
            clear()
            print(now.strftime("%Y-%m-%d %H:%M"))
            wait_time = 60 - datetime.now().second
            event.wait(timeout=wait_time)


if __name__ == '__main__':
    event = Event()
    t1 = Thread(target=background_thread)
    t2 = Thread(target=reader)
    t1.start()
    t2.start()
