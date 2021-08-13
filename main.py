#!/usr/bin/env python
from datetime import datetime
from datetime import timedelta
import time
import csv
from threading import *
import requests
import mariadb
import sys
import os

thread_running = True
token = "nhT4TzFE5b0NO3YMiMUlXexfqJrK23CAyyHuQyDEdP3"


def clear():
    print("\033c")


def line_notify_message(token, msg):
    headers = {
        "Authorization": "Bearer " + token,
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
    sql = "SELECT userid FROM attendance INNER JOIN users USING(userid) WHERE clockout is NULL AND chipno=? AND clockday =?"
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
    sql = "SELECT clockin FROM attendance INNER JOIN users USING(userid) WHERE (clockout >= ? OR clockin >= ?) AND " \
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
        sql = "INSERT INTO attendance(userid, username, clockday, clockin)" \
              "VALUES (?,?,?,?)"
        par = (userid, name, todays_date, come_time)
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
        par = (mychip,)
        go_time = datetime.now().strftime("%H:%M")
        todays_date = datetime.now().strftime("%Y-%m-%d")
        cur = conn.cursor()
        sql = "SELECT userid, name FROM users WHERE chipno = ?"
        cur.execute(sql, par)
        userid, name = cur.fetchone()
        sql = "UPDATE attendance SET clockout = ? WHERE userid = ? AND clockout is NULL AND clockday = ?"
        par = (go_time, userid, todays_date)
        cur.execute(sql, par)
        conn.commit()
        print(name + " " + go_time + " " + "下班")
    else:
        print("已打卡了")


def export_data(conn):
    month = datetime.now().month
    year = datetime.now().year - 1911
    str_year = str(year)
    str_month = str(month).zfill(2)
    cur = conn.cursor()
    csv_writer = csv.writer(open("打卡-" + str_year + "-" + str_month + ".csv", "w", encoding='utf-8-sig', newline=''))
    sql = "SELECT username, clockday, DATE_FORMAT(clockin,'%k:%i') as 'clockin', DATE_FORMAT(clockout,'%k:%i') as " \
          "'clockout' FROM attendance where month(clockday) = month(curdate()) ORDER BY userid ASC, clockday ASC "
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
            event.wait(timeout=60)


if __name__ == '__main__':
    event = Event()
    t1 = Thread(target=background_thread)
    t2 = Thread(target=reader)
    t1.start()
    t2.start()