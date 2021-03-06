#!/usr/bin/env python

# -----------------------------------------------------------------------
# database.py
# Author: Shift Scheduler Team
# -----------------------------------------------------------------------

from sqlite3 import connect
from sys import stderr
import os
from shift import Shift
from employee import Employee

import psycopg2
import datetime
from configparser import ConfigParser


# -----------------------------------------------------------------------

class Database:

    def _init_(self):
        self._conn = None

    def connect(self):
        """ Connect to the PostgreSQL database server """
        self._conn = None
        try:
            print('Connecting to the PostgreSQL database...')

            # DATABASE_URL = os.environ['DATABASE_URL']
            DATABASE_URL = "postgres://qxcsbcdzxdftyo:6034a3745c758509ba1c815e3507925ae54fbef58258edea409b7d0958fe0002@ec2-34-204-22-76.compute-1.amazonaws.com:5432/d6c9olgrm57o3s"
            self._conn = psycopg2.connect(DATABASE_URL, sslmode='require')

        except (Exception, psycopg2.DatabaseError) as error:
            print('Error: ' + str(error))

    def disconnect(self):
        self._conn.close()
        print('Database connection closed.')

    #-----------------------------------------------------------------------

    def shiftDetails(self, dateIn, task_id):

        try:
            # create a cursor
            cur = self._conn.cursor()

            shiftDate = datetime.date.fromisoformat(dateIn)
            QUERY_STRING = 'SELECT shift_info.shift_id, shift_info.date,' + \
                           'shift_info.task_id, task_info.meal, task_info.task,' + \
                           'task_info.start_time, task_info.end_time, shift_info.cur_people FROM shift_info,' + \
                           'task_info WHERE shift_info.task_id = task_info.task_id AND ' + \
                           'shift_info.date = %s AND task_info.task_id = %s'
            cur.execute(QUERY_STRING, (shiftDate, task_id))

            row = cur.fetchone()
            shift = Shift(row[0], str(row[1]), row[2], row[3], row[4], row[5], row[6], row[7])
            cur.close()
            return shift
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def shiftFromID(self, shiftId):

        try:
            # create a cursor
            cur = self._conn.cursor()

            QUERY_STRING = 'SELECT shift_info.shift_id, shift_info.date,' + \
                           'shift_info.task_id, task_info.meal, task_info.task,' + \
                           'task_info.start_time, task_info.end_time, shift_info.cur_people FROM shift_info,' + \
                           'task_info WHERE shift_info.task_id = task_info.task_id AND ' + \
                           'shift_info.shift_id = %s'
            cur.execute(QUERY_STRING, (shiftId,))

            row = cur.fetchone()
            shift = Shift(row[0], str(row[1]), row[2], row[3], row[4], row[5], row[6], row[7])
            cur.close()
            return shift
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def subOut(self, netid, dateIn, taskId):
        try:
            cur = self._conn.cursor()
            shiftDate = datetime.date.fromisoformat(dateIn)
            if shiftDate < datetime.datetime.now().date():
                print('SubOut requested for an old shift.')
                return "old"

            shiftDate = datetime.date.fromisoformat(dateIn)

            QUERY_STRING = 'SELECT shift_info.shift_id FROM shift_info ' + \
                           'WHERE shift_info.task_id = %s ' + \
                           'AND shift_info.date = %s'
            cur.execute(QUERY_STRING, (taskId, shiftDate))
            row = cur.fetchone()
            shiftId = row[0]

            if not self.unassignShift(netid, shiftId):
                print("Unassignment failed")
                cur.close()
                return False

            QUERY_STRING = 'SELECT sub_requests.shift_id FROM sub_requests ' + \
                           'WHERE sub_requests.sub_in_netid = %s ' + \
                           'AND sub_requests.shift_id = %s'
            cur.execute(QUERY_STRING, (netid, shiftId))
            row = cur.fetchone()
            if row is not None:
                QUERY_STRING = 'UPDATE sub_requests SET sub_in_netid = %s WHERE ' + \
                               'sub_requests.sub_in_netid = %s AND sub_requests.shift_id = %s'
                cur.execute(QUERY_STRING, ('needed', netid, shiftId))
                self._conn.commit()

                # decrement # of subins of the employee
                QUERY_STRING = 'UPDATE employees SET subins = subins - 1 WHERE netid=%s AND subins > 0'
                cur.execute(QUERY_STRING, (netid,))
                self._conn.commit()

                print('Sub request is committed.')
                cur.close()
                return True

            else:
                QUERY_STRING = 'INSERT INTO sub_requests (shift_id, sub_out_netid, sub_in_netid) VALUES ' + \
                               '(%s, %s, %s);'
                cur.execute(QUERY_STRING, (shiftId, netid, 'needed'))
                self._conn.commit()

                # increment # of subouts of the employee
                QUERY_STRING = 'UPDATE employees SET subouts = subouts + 1 WHERE netid=%s'
                cur.execute(QUERY_STRING, (netid,))
                self._conn.commit()

                print('Sub request is committed.')
                cur.close()
                return True

        except (Exception, psycopg2.DatabaseError) as error:
            self._conn.rollback()
            print('Sub request rolled back.')
            print(error)
            return False

    #-----------------------------------------------------------------------

    def subIn(self, netid, dateIn, taskId):
        try:
            cur = self._conn.cursor()
            shiftDate = datetime.date.fromisoformat(dateIn)
            if shiftDate < datetime.datetime.now().date():
                print('SubOut requested for an old shift.')
                cur.close()
                return "old"

            shiftDate = datetime.date.fromisoformat(dateIn)

            QUERY_STRING = 'SELECT shift_info.shift_id, sub_requests.sub_out_netid ' + \
                           'FROM shift_info, sub_requests ' + \
                           'WHERE shift_info.task_id = %s ' + \
                           'AND shift_info.date = %s ' + \
                           'AND shift_info.shift_id = sub_requests.shift_id AND sub_requests.sub_in_netid = %s'
            cur.execute(QUERY_STRING, (taskId, shiftDate, 'needed'))
            row = cur.fetchone()
            shiftId = row[0]
            otherNetid = row[1]

            assign = self.assignShift(netid, shiftId)
            if assign == "conflict":
                cur.close()
                return assign
            elif assign == "already_assigned":
                cur.close()
                return assign
            elif not assign:
                print("Shift assignment failed.")
                cur.close()
                return False

            if otherNetid == netid:
                QUERY_STRING = 'DELETE FROM sub_requests WHERE shift_id = %s AND sub_out_netid = %s'
                cur.execute(QUERY_STRING, (shiftId, netid))
                self._conn.commit()

                # decrement # of subouts of the employee
                QUERY_STRING = 'UPDATE employees SET subouts = subouts - 1 WHERE netid=%s AND subouts > 0'
                cur.execute(QUERY_STRING, (netid,))
                self._conn.commit()

                print('Sub pick-up is committed.')
                cur.close()
                return True

            else:
                # update sub_requests table
                QUERY_STRING = 'UPDATE sub_requests ' + \
                               'SET sub_in_netid = %s' + \
                               'WHERE sub_requests.shift_id = %s ' + \
                               'AND sub_requests.sub_out_netid = %s'
                cur.execute(QUERY_STRING, (netid, shiftId, otherNetid))
                self._conn.commit()

                # increment # of subins of the employee
                QUERY_STRING = 'UPDATE employees SET subins = subins + 1 WHERE netid=%s'
                cur.execute(QUERY_STRING, (netid,))
                self._conn.commit()

                print('Sub pick-up is committed.')
                cur.close()
                return True


        except (Exception, psycopg2.DatabaseError) as error:
            self._conn.rollback()
            print('Sub pick-up rolled back.')
            print(error)
            return False

    #-----------------------------------------------------------------------

    # currently returns a list of shift objects
    def allSubNeeded(self):
        try:
            cur = self._conn.cursor()

            QUERY_STRING = 'SELECT sub_requests.shift_id FROM sub_requests ' + \
                           'WHERE sub_requests.sub_in_netid = %s'
            cur.execute(QUERY_STRING, ('needed',))

            row = cur.fetchone()
            shiftsNeeded = []
            while row is not None:
                shiftsNeeded.append(row[0])
                row = cur.fetchone()
            cur.close()

            shiftObjects = []
            for shift in shiftsNeeded:
                shiftObject = self.shiftFromID(shift)
                shiftObjects.append(shiftObject)
            return shiftObjects
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return []

    #-----------------------------------------------------------------------

    # currently returns a list of shift objects
    def allSubNeededForEmployee(self, netid):
        try:
            cur = self._conn.cursor()

            QUERY_STRING = 'SELECT sub_requests.shift_id FROM sub_requests ' + \
                           'WHERE sub_requests.sub_in_netid = %s'
            cur.execute(QUERY_STRING, ('needed',))

            rows = cur.fetchall()
            shiftsNeeded = []
            if rows is not None:
                for row in rows:
                    shiftid = row[0]
                    QUERY_STRING = 'SELECT * FROM shift_assign WHERE shift_id=%s AND netid=%s'
                    cur.execute(QUERY_STRING, (shiftid, netid))
                    row2 = cur.fetchone()
                    if row2 is None:
                        shiftsNeeded.append(shiftid)
            cur.close()

            shiftObjects = []
            for shift in shiftsNeeded:
                shiftObject = self.shiftFromID(shift)
                shiftObjects.append(shiftObject)
            return shiftObjects
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return []

    #-----------------------------------------------------------------------

    def allSubsForDate(self, date):
        subsList = self.allSubNeeded()

        dateSubs = []
        for sub in subsList:
            if (sub.getDate() == date):
                dateSubs.append(sub)
        return dateSubs

    #-----------------------------------------------------------------------

    def allSubsForWeek(self, date):
        subsList = self.allSubNeeded()

        if datetime.date.fromisoformat(date).weekday() != 0:
            print("Given date is not a Monday.")
            return -1

        monday = datetime.date.fromisoformat(date)
        tuesday = monday + datetime.timedelta(days=1)
        wednesday = tuesday + datetime.timedelta(days=1)
        thursday = wednesday + datetime.timedelta(days=1)
        friday = thursday + datetime.timedelta(days=1)
        saturday = friday + datetime.timedelta(days=1)
        sunday = saturday + datetime.timedelta(days=1)
        week = [monday, tuesday, wednesday, thursday, friday, saturday, sunday]

        weekFormatted = []
        for day in week:
            dayFormatted = day.isoformat()
            weekFormatted.append(dayFormatted)

        retSubs = []
        for sub in subsList:
            if (sub.getDate() in weekFormatted):
                retSub = str(datetime.date.fromisoformat(sub.getDate()).weekday()) + '-' + sub.getTaskID()
                retSubs.append(retSub)

        return retSubs

    #-----------------------------------------------------------------------

    def allSubsForEmployee(self, date, netid):
        subsList = self.allSubNeededForEmployee(netid)

        if datetime.date.fromisoformat(date).weekday() != 0:
            print("Given date is not a Monday.")
            return -1

        monday = datetime.date.fromisoformat(date)
        tuesday = monday + datetime.timedelta(days=1)
        wednesday = tuesday + datetime.timedelta(days=1)
        thursday = wednesday + datetime.timedelta(days=1)
        friday = thursday + datetime.timedelta(days=1)
        saturday = friday + datetime.timedelta(days=1)
        sunday = saturday + datetime.timedelta(days=1)
        week = [monday, tuesday, wednesday, thursday, friday, saturday, sunday]

        weekFormatted = []
        for day in week:
            dayFormatted = day.isoformat()
            weekFormatted.append(dayFormatted)

        retSubs = []
        for sub in subsList:
            if (sub.getDate() in weekFormatted):
                retSub = str(datetime.date.fromisoformat(sub.getDate()).weekday()) + '-' + sub.getTaskID()
                retSubs.append(retSub)

        return retSubs

    #-----------------------------------------------------------------------

    def myShiftsOld(self, netid, dateIn):
        try:
            def convertDay(dayString):
                if (dayString == 'monday'): return '0'
                if (dayString == 'tuesday'): return '1'
                if (dayString == 'wednesday'): return '2'
                if (dayString == 'thursday'): return '3'
                if (dayString == 'friday'): return '4'
                if (dayString == 'saturday'): return '5'
                if (dayString == 'sunday'): return '6'

            displayDate = datetime.date.fromisoformat(dateIn)

            cur = self._conn.cursor()

            # get netid's all regular shifts
            QUERY_STRING = 'SELECT regular_shifts.task_id, regular_shifts.dotw ' + \
                           'FROM regular_shifts ' + \
                           'WHERE regular_shifts.netid = %s'
            cur.execute(QUERY_STRING, (netid,))

            row = cur.fetchone()
            regShifts = []
            while row is not None:
                regShift = convertDay(row[1]) + '-' + str(row[0])
                if regShift not in regShifts:
                    regShifts.append(regShift)
                    # print("A: " + str(regShift))
                row = cur.fetchone()

            # get netid's all subbed in shifts
            QUERY_STRING = 'SELECT sub_requests.shift_id ' + \
                           'FROM sub_requests WHERE sub_in_netid = %s'
            cur.execute(QUERY_STRING, (netid,))
            row = cur.fetchone()
            while row is not None:
                subbedInShift = self.shiftFromID(row[0])
                subbedInShiftDate = datetime.date.fromisoformat(subbedInShift.getDate())
                if (subbedInShiftDate >= displayDate) and (subbedInShiftDate <= displayDate + datetime.timedelta(weeks=1)):
                    regShift = str(datetime.date.fromisoformat(subbedInShift.getDate()).weekday()) + '-' + str(subbedInShift.getTaskID())
                    if regShift not in regShifts:
                        regShifts.append(regShift)
                        # print("B: " + str(regShift))
                row = cur.fetchone()

            # remove netid's subbed out shifts
            QUERY_STRING = 'SELECT sub_requests.shift_id ' + \
                           'FROM sub_requests WHERE sub_out_netid = %s'
            cur.execute(QUERY_STRING, (netid,))
            rows = cur.fetchall()
            if rows is not None:
                for row in rows:
                    subbedOutShift = self.shiftFromID(row[0])
                    subbedOutShiftDate = datetime.date.fromisoformat(subbedOutShift.getDate())
                    if (subbedOutShiftDate >= displayDate) and (subbedOutShiftDate <= displayDate + datetime.timedelta(weeks=1)):
                        outShift = str(datetime.date.fromisoformat(subbedOutShift.getDate()).weekday()) + '-' + str(subbedOutShift.getTaskID())
                        if outShift in regShifts:
                            regShifts.remove(outShift)
                            # print("C: " + str(outShift))
            cur.close()

            # for shift in regShifts:
                # print("D: " + str(shift))
            return regShifts

        except (Exception, psycopg2.DatabaseError) as error:
            print("there is an error")
            print(error)
            return False

    #-----------------------------------------------------------------------

    def myShifts(self, netid, dateIn):
        try:
            displayDate = datetime.date.fromisoformat(dateIn)

            cur = self._conn.cursor()

            # get netid's shifts from shift_assign
            QUERY_STRING = 'SELECT shift_id FROM shift_assign WHERE netid=%s' + \
                            'INTERSECT SELECT shift_id FROM shift_info WHERE shift_info.date >= %s AND shift_info.date < %s'
            cur.execute(QUERY_STRING, (netid, dateIn, (displayDate + datetime.timedelta(weeks=1)).isoformat()))


            myShifts = []
            row = cur.fetchone()
            while row is not None:
                myShiftObj = self.shiftFromID(row[0])
                print(datetime.date.fromisoformat(myShiftObj.getDate()).weekday())
                myShiftStr = str(datetime.date.fromisoformat(myShiftObj.getDate()).weekday()) + '-' + str(myShiftObj.getTaskID())
                if myShiftStr not in myShifts:
                    myShifts.append(myShiftStr)
                row = cur.fetchone()

            cur.close()
            print(myShifts)
            return myShifts

        except (Exception, psycopg2.DatabaseError) as error:
            print("There was an error in myShifts() method")
            print(error)
            return False

    #-----------------------------------------------------------------------

    def regularShifts(self, netid):
        try:
            def convertDay(dayString):
                if (dayString == 'monday'): return '0'
                if (dayString == 'tuesday'): return '1'
                if (dayString == 'wednesday'): return '2'
                if (dayString == 'thursday'): return '3'
                if (dayString == 'friday'): return '4'
                if (dayString == 'saturday'): return '5'
                if (dayString == 'sunday'): return '6'

            cur = self._conn.cursor()

            # get netid's all regular shifts
            QUERY_STRING = 'SELECT regular_shifts.task_id, regular_shifts.dotw ' + \
                           'FROM regular_shifts ' + \
                           'WHERE regular_shifts.netid = %s'
            cur.execute(QUERY_STRING, (netid,))

            row = cur.fetchone()
            regShifts = []
            while row is not None:
                regShift = convertDay(row[1]) + '-' + str(row[0]) # Convention: dayNo-taskId
                if regShift not in regShifts:
                    regShifts.append(regShift)
                row = cur.fetchone()

            cur.close()
            regShifts.sort(key=str.lower)
            return regShifts

        except (Exception, psycopg2.DatabaseError) as error:
            print("there is an error")
            print(error)
            return False

    #-----------------------------------------------------------------------


    def addRegularShift(self, netid, taskid, dotw):
        try:
            if dotw == 'monday' or dotw == 'tuesday' or dotw == 'wednesday' or dotw == 'thursday' or dotw == 'friday':
                if taskid == 7 or taskid == 8 or taskid == 9 or taskid == 10 or taskid == 11  or taskid == 12:
                    print("Shift not valid.")
                    return "not_valid"

            if dotw != 'friday':
                if taskid == 13:
                    print("Shift not valid.")
                    return "not_valid"

            def convertDay(dayString):
                if (dayString == 'monday'): return '0'
                if (dayString == 'tuesday'): return '1'
                if (dayString == 'wednesday'): return '2'
                if (dayString == 'thursday'): return '3'
                if (dayString == 'friday'): return '4'
                if (dayString == 'saturday'): return '5'
                if (dayString == 'sunday'): return '6'

            def convertDayReverse(dayNumber):
                if (dayNumber == 0): return 'monday'
                if (dayNumber == 1): return 'tuesday'
                if (dayNumber == 2): return 'wednesday'
                if (dayNumber == 3): return 'thursday'
                if (dayNumber == 4): return 'friday'
                if (dayNumber == 5): return 'saturday'
                if (dayNumber == 6): return 'sunday'

            cur = self._conn.cursor()

            # check if this regular shift is already assigned to netid
            checkString = convertDay(dotw) + '-' + str(taskid)
            netidRegShifts = self.regularShifts(netid)
            if checkString in netidRegShifts:
                print("RegularShift is already assigned")
                cur.close()
                return "already_assigned"

            # Check if there is a conflict
            for regShift in netidRegShifts:
                regShiftDay = regShift.split("-")[0]
                if regShiftDay == convertDay(dotw):
                    regShiftTask = int(regShift.split("-")[1])
                    if self._checkTaskConflicts(int(taskid), [regShiftTask]):
                        print("There is a shift conflict")
                        cur.close()
                        return "conflict"

            # add to regular shifts
            QUERY_STRING = 'INSERT INTO regular_shifts(netid, task_id, dotw) VALUES (%s, %s, %s)'
            cur.execute(QUERY_STRING, (netid, taskid, dotw))
            self._conn.commit()
            print('Added regular shift: ' + str(taskid) + ' on ' + str(dotw) + ' to '  + str(netid))

            # find shift ids with given taskid and dotw
            QUERY_STRING = 'SELECT shift_id, date FROM shift_info WHERE task_id=%s'
            cur.execute(QUERY_STRING, (taskid,))
            row = cur.fetchone()
            shiftsToAdd = []
            while row is not None:
                shift = row[0]
                date = datetime.date.fromisoformat(str(row[1]))
                if date >= datetime.date.today():
                    day = date.weekday()
                    if (convertDayReverse(day) == dotw) and (shift not in shiftsToAdd):
                        shiftsToAdd.append(shift)
                row = cur.fetchone()

            # assign all the shifts in shiftsToAdd to netid in shift_assign table
            for shiftid in shiftsToAdd:
                QUERY_STRING = 'SELECT * FROM shift_assign WHERE shift_id=%s AND netid=%s'
                cur.execute(QUERY_STRING, (shiftid, netid))
                row = cur.fetchone()
                if row is None:
                    QUERY_STRING = 'INSERT INTO shift_assign(shift_id, netid) VALUES (%s, %s)'
                    cur.execute(QUERY_STRING, (shiftid, netid))
                    self._conn.commit()
                    print('Added regular shift to shift_assign: ' + str(shiftid))

            cur.close()
            return True

        except (Exception, psycopg2.DatabaseError) as error:
            self._conn.rollback()
            print('Could not add the regular shift.')
            print(error)
            return False

    #-----------------------------------------------------------------------

    def removeRegularShift(self, netid, taskid, dotw):
        try:
            def convertDayReverse(dayNumber):
                if (dayNumber == 0): return 'monday'
                if (dayNumber == 1): return 'tuesday'
                if (dayNumber == 2): return 'wednesday'
                if (dayNumber == 3): return 'thursday'
                if (dayNumber == 4): return 'friday'
                if (dayNumber == 5): return 'saturday'
                if (dayNumber == 6): return 'sunday'

            # create a cursor
            cur = self._conn.cursor()

            QUERY_STRING = 'SELECT regular_shifts.netid, regular_shifts.task_id, regular_shifts.dotw FROM regular_shifts WHERE netid = %s AND task_id = %s AND dotw = %s'
            print('hello there')
            cur.execute(QUERY_STRING, (netid, taskid, dotw,))
            print('general kenobi')

            # check that shiftid exists
            row = cur.fetchone()
            if row is None:
                print('Regular shift does not exist.')
                cur.close()
                return False

            # delete from regular shifts
            QUERY_STRING = 'DELETE FROM regular_shifts WHERE netid = %s AND task_id = %s AND dotw = %s'
            cur.execute(QUERY_STRING, (netid, taskid, dotw))
            self._conn.commit()
            print('Removed regular shift: ' + str(taskid) + ' on ' + str(dotw) + ' from '  + str(netid))

            # find shift ids with given taskid and dotw
            QUERY_STRING = 'SELECT shift_id, date FROM shift_info WHERE task_id=%s'
            cur.execute(QUERY_STRING, (taskid,))
            row = cur.fetchone()
            shiftsToRemove = []
            while row is not None:
                shift = row[0]
                date = datetime.date.fromisoformat(str(row[1]))
                day = date.weekday()
                if date >= datetime.date.today():
                    if (convertDayReverse(day) == dotw) and (shift not in shiftsToRemove):
                        shiftsToRemove.append(shift)
                row = cur.fetchone()

            # remove all the shifts in shiftsToRemove for netid from shift_assign table
            for shiftid in shiftsToRemove:
                QUERY_STRING = 'DELETE FROM shift_assign where shift_id=%s AND netid=%s'
                cur.execute(QUERY_STRING, (shiftid, netid))
                self._conn.commit()
                print('Remove regular shift from shift_assign: ' + str(shiftid))

            cur.close()
            return True

        except (Exception, psycopg2.DatabaseError) as error:
            self._conn.rollback()
            print('Could not remove the regular shift.')
            print(error)
            return False

    #-----------------------------------------------------------------------

    def populateShiftInfo(self, dateIn):

        try:
            if datetime.date.fromisoformat(dateIn).weekday() != 0:
                print("Given date is not a Monday.")
                return False

            date = datetime.date.fromisoformat(dateIn)
            cur = self._conn.cursor()

            def convertDayReverse(dayNumber):
                if (dayNumber == 0): return 'monday'
                if (dayNumber == 1): return 'tuesday'
                if (dayNumber == 2): return 'wednesday'
                if (dayNumber == 3): return 'thursday'
                if (dayNumber == 4): return 'friday'
                if (dayNumber == 5): return 'saturday'
                if (dayNumber == 6): return 'sunday'

            QUERY_STRING = 'SELECT * FROM max_shift_id'
            cur.execute(QUERY_STRING)
            row = cur.fetchone()

            shift_id = int(row[0])
            for i in range(7):
                for j in range(1, 7):
                    QUERY_STRING = 'SELECT regular_shifts.netid FROM regular_shifts WHERE task_id = %s AND dotw = %s'
                    cur.execute(QUERY_STRING, (j, convertDayReverse(i)))

                    numPeople = 0
                    rows = cur.fetchall()
                    for row in rows:
                        netid = row[0]
                        QUERY_STRING = 'INSERT INTO shift_assign(shift_id, netid) VALUES (%s, %s)'
                        cur.execute(QUERY_STRING, (shift_id, netid))
                        print('Added entry to shift_assign:' + str(shift_id) + ' ' + str(netid))
                        self._conn.commit()
                        numPeople += 1

                    QUERY_STRING = 'INSERT INTO shift_info(shift_id, date, task_id, cur_people) VALUES ' + \
                                   '(%s, %s, %s, %s);'
                    cur.execute(QUERY_STRING, (shift_id, date.isoformat(), j, numPeople))
                    self._conn.commit()
                    print('Added entry to shift_info:' + str(shift_id) + ' ' + str(date) + ' ' + str(j) + ' ' + str(
                        numPeople))
                    shift_id += 1

                if (i > 4):
                    for j in range(7, 13):
                        QUERY_STRING = 'SELECT regular_shifts.netid FROM regular_shifts WHERE task_id = %s AND dotw = %s'
                        cur.execute(QUERY_STRING, (j, convertDayReverse(i)))

                        numPeople = 0
                        rows = cur.fetchall()
                        for row in rows:
                            netid = row[0]
                            QUERY_STRING = 'INSERT INTO shift_assign(shift_id, netid) VALUES (%s, %s)'
                            cur.execute(QUERY_STRING, (shift_id, netid))
                            print('Added entry to shift_assign:' + str(shift_id) + ' ' + str(netid))
                            self._conn.commit()
                            numPeople += 1

                        QUERY_STRING = 'INSERT INTO shift_info(shift_id, date, task_id, cur_people) VALUES ' + \
                                       '(%s, %s, %s, %s);'
                        cur.execute(QUERY_STRING, (shift_id, date.isoformat(), j, numPeople))
                        self._conn.commit()
                        print('Added entry to shift_info:' + str(shift_id) + ' ' + str(date) + ' ' + str(j) + ' ' + str(
                            numPeople))
                        shift_id += 1

                if (i == 4):
                    QUERY_STRING = 'SELECT regular_shifts.netid FROM regular_shifts WHERE task_id = %s AND dotw = %s'
                    cur.execute(QUERY_STRING, (13, convertDayReverse(i)))

                    numPeople = 0
                    rows = cur.fetchall()
                    for row in rows:
                        netid = row[0]
                        QUERY_STRING = 'INSERT INTO shift_assign(shift_id, netid) VALUES (%s, %s)'
                        cur.execute(QUERY_STRING, (shift_id, netid))
                        print('Added entry to shift_assign:' + str(shift_id) + ' ' + str(netid))
                        self._conn.commit()
                        numPeople += 1

                    QUERY_STRING = 'INSERT INTO shift_info(shift_id, date, task_id, cur_people) VALUES ' + \
                                   '(%s, %s, %s, %s);'
                    cur.execute(QUERY_STRING, (shift_id, date.isoformat(), 13, numPeople))
                    self._conn.commit()
                    print('Added entry to shift_info:' + str(shift_id) + ' ' + str(date) + ' ' + str(13) + ' ' + str(
                        numPeople))
                    shift_id += 1

                date += datetime.timedelta(days=1)

            QUERY_STRING = 'UPDATE max_shift_id SET shift_id = %s, date = %s'
            cur.execute(QUERY_STRING, (shift_id, datetime.date.today().isoformat()))
            self._conn.commit()
            cur.close()
            return True

        except (Exception, psycopg2.DatabaseError) as error:
            self._conn.rollback()
            print('Could not populate shift_info table.')
            print(error)
            return False

    #-----------------------------------------------------------------------

    def populateForPeriod(self, start, end):

        try:
            if datetime.date.fromisoformat(start).weekday() != 0:
                print("Given date is not a Monday.")
                return False

            dateStart = datetime.date.fromisoformat(start)
            dateEnd = datetime.date.fromisoformat(end)
            cur = self._conn.cursor()

            while dateStart < dateEnd:
                self.populateShiftInfo(start)
                deltaWeek = datetime.timedelta(weeks = 1)
                dateStart += deltaWeek
                start = dateStart.isoformat()

        except (Exception, psycopg2.DatabaseError) as error:
            print('Could not populate the tables.')
            print(error)
            return False

    #-----------------------------------------------------------------------

    def employeeDetails(self, netid):

        try:
            # create a cursor
            cur = self._conn.cursor()

            QUERY_STRING = 'SELECT netid FROM employees WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))

            row = cur.fetchone()
            if row is None:
                print('Employee does not exist.')
                cur.close()
                return 'Employee does not exist.'

            QUERY_STRING = 'SELECT * FROM employees WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))

            row = cur.fetchone()
            employee = Employee(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10])
            cur.close()
            return employee

        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def getAllEmployees(self):

        try:
            #create a cursor
            cur = self._conn.cursor()
            QUERY_STRING = 'SELECT * FROM employees'
            cur.execute(QUERY_STRING, ())

            employeeList = []
            rows = cur.fetchall()
            if rows is not None:
                for row in rows:
                    employee = Employee(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10])
                    employeeList.append(employee)
            cur.close()
            employeeListSorted = sorted(employeeList, key=lambda x: x._first_name.lower())
            return employeeListSorted
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def insertEmployee(self, netid, first_name, last_name, manager):

        try:
            if (not netid) or (not first_name) or (not last_name) or (not manager):
                print('Please enter all required information.')
                return False

            # create a cursor
            cur = self._conn.cursor()

            QUERY_STRING = 'SELECT netid FROM employees WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))

            row = cur.fetchone()
            if row is not None:
                print('Employee already exists.')
                cur.close()
                return False
            email = netid + '@princeton.edu'
            QUERY_STRING = 'INSERT INTO employees (netid, first_name, last_name, hours, total_hours, email, manager, subins, subouts, walkons, noshows) ' + \
                           'VALUES (%s, %s, %s, 0, 0, %s, %s, 0, 0, 0, 0)'
            cur.execute(QUERY_STRING, (netid, first_name, last_name, email, manager))
            self._conn.commit()
            print('Added employee: ' + netid + ' ' + first_name + ' ' + last_name + ' ' + manager)

            cur.close()
            return True

        except (Exception, psycopg2.DatabaseError) as error:
            self._conn.rollback()
            print('Could not add the employee.')
            print(error)
            return False

    #-----------------------------------------------------------------------

    def removeEmployee(self, netid):

        try:
            if not netid:
                print('Please enter all required information.')
                return False

            # create a cursor
            cur = self._conn.cursor()

            QUERY_STRING = 'SELECT netid FROM employees WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))

            row = cur.fetchone()
            if row is None:
                print('Employee does not exist.')
                cur.close()
                return "not_employee"

            QUERY_STRING = 'DELETE FROM employees WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))
            self._conn.commit()
            print('Removed employee: ' + netid)
            cur.close()
            return True

        except (Exception, psycopg2.DatabaseError) as error:
            self._conn.rollback()
            print('Could not remove the employee.')
            print(error)
            return False

    #-----------------------------------------------------------------------

    def assignShift(self, netid, shiftid):
        try:
            if (not netid) or (shiftid is None):
                print('Please enter all required information.')
                return False

            # create a cursor
            cur = self._conn.cursor()

            # Check if netid exists
            QUERY_STRING = 'SELECT netid FROM employees WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))

            row = cur.fetchone()
            if row is None:
                print('Employee does not exist.')
                cur.close()
                return False

            # Check if shiftid exists
            QUERY_STRING = 'SELECT shift_id FROM shift_info WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            row = cur.fetchone()
            if row is None:
                print('Shift does not exist.')
                cur.close()
                return False

            # Check if shift-netid pair is already in the table
            QUERY_STRING = 'SELECT * FROM shift_assign WHERE shift_id = %s AND netid = %s'
            cur.execute(QUERY_STRING, (shiftid, netid))
            row = cur.fetchone()
            if row is not None:
                print('Employee is already assigned to this shift.')
                cur.close()
                return "already_assigned"

            # Check if there is a conflicting shift
            shiftObj = self.shiftFromID(shiftid)
            QUERY_STRING = 'SELECT shift_id FROM shift_assign WHERE netid=%s' + \
                            'INTERSECT SELECT shift_id FROM shift_info WHERE shift_info.date=%s'
            cur.execute(QUERY_STRING, (netid, shiftObj.getDate()))

            taskIds = []
            rows = cur.fetchall()
            if rows is not None:
                for row in rows:
                    print(row[0])
                    taskId = int(self.shiftFromID(row[0]).getTaskID())
                    if taskId not in taskIds:
                        taskIds.append(taskId)

            if self._checkTaskConflicts(int(shiftObj.getTaskID()), taskIds):
                print('There is a conflict with another shift.')
                cur.close()
                return "conflict"

            # Insert into shift_assign
            QUERY_STRING = 'INSERT INTO shift_assign(shift_id, netid) VALUES (%s, %s)'
            cur.execute(QUERY_STRING, (shiftid, netid))
            self._conn.commit()
            print('Added shift-employee pair: ' + str(shiftid) + ' ' + netid)

            # Update shift_info
            QUERY_STRING = 'UPDATE shift_info SET cur_people = cur_people + 1 WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))
            self._conn.commit()
            print('Incremented current people for shift: ' + str(shiftid))
            cur.close()
            return True

        except (Exception, psycopg2.DatabaseError) as error:
            self._conn.rollback()
            print('Could not assign the shift to employee.')
            print(error)
            return False

    #-----------------------------------------------------------------------

    # returns true if there are conflicts and false if no conflicts
    def _checkTaskConflicts(self, task, tasks):
        print(task)
        print(tasks)
        conflicts = [[2, 3, 4, 5, 6], [1, 4, 5], [1, 4, 6], [1, 2, 3, 5, 6], [1, 2, 4], [1, 3, 4], [8, 9, 10, 11, 12], [7, 10, 11], [7, 10, 12], [7, 8, 9, 11, 12], [7, 8, 10], [7, 9, 10]]
        for num in tasks:
            if (num in conflicts[task - 1]):
                return True
        return False

    #-----------------------------------------------------------------------

    def unassignShift(self, netid, shiftid):
        print("is it here?")
        try:
            if (not netid) or (shiftid is None):
                print('Please enter all required information.')
                return False

            # create a cursor
            cur = self._conn.cursor()

            # Check if netid exists
            QUERY_STRING = 'SELECT netid FROM employees WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))

            row = cur.fetchone()
            if row is None:
                print('Employee does not exist.')
                cur.close()
                return False

            # Check if shiftid exists
            QUERY_STRING = 'SELECT shift_id FROM shift_info WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            row = cur.fetchone()
            if row is None:
                print('Shift does not exist.')
                cur.close()
                return False

            # Check if shift-netid pair is already in the table
            QUERY_STRING = 'SELECT * FROM shift_assign WHERE shift_id = %s AND netid = %s'
            cur.execute(QUERY_STRING, (shiftid, netid))
            row = cur.fetchone()
            if row is None:
                print('Employee is not assigned to this shift.')
                cur.close()
                return False

            # Remove from shift_assign
            QUERY_STRING = 'DELETE FROM shift_assign WHERE shift_id = %s AND netid = %s'
            cur.execute(QUERY_STRING, (shiftid, netid))
            self._conn.commit()
            print('Removed shift-employee pair: ' + str(shiftid) + ' ' + netid)

            # Update shift_info
            QUERY_STRING = 'UPDATE shift_info SET cur_people = cur_people - 1 WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))
            self._conn.commit()
            print('Decremented current people for shift: ' + str(shiftid))

            cur.close()
            return True

        except (Exception, psycopg2.DatabaseError) as error:
            self._conn.rollback()
            print('Could not unassign the shift to employee.')
            print(error)
            return False

    #-----------------------------------------------------------------------

    def employeesInShift(self, shiftid):
        try:
            # create a cursor
            cur = self._conn.cursor()

            # Check if shiftid exists
            QUERY_STRING = 'SELECT shift_id FROM shift_info WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            row = cur.fetchone()
            if row is None:
                print('Shift does not exist.')
                cur.close()
                return False

            # Get all employee netids working in the shift
            QUERY_STRING = 'SELECT netid FROM shift_assign WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            employeeNetids = []
            rows = cur.fetchall()
            if rows is not None:
                for row in rows:
                    netid = row[0]
                    if netid not in employeeNetids:
                        employeeNetids.append(netid)

            # Subtract employees that are added through walk on
            QUERY_STRING = 'SELECT netid FROM walkons WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            rows = cur.fetchall()
            if rows is not None:
                for row in rows:
                    netidRemove = row[0]
                    if netidRemove in employeeNetids:
                        employeeNetids.remove(netidRemove)

            # Get all employee full names working in the shift
            employeeFullNames = []
            for netid in employeeNetids:
                QUERY_STRING = 'SELECT first_name, last_name FROM employees WHERE netid = %s'
                cur.execute(QUERY_STRING, (netid,))

                row = cur.fetchone()
                if row is not None:
                    fullName = row[0] + ' ' + row[1]
                    if fullName not in employeeFullNames:
                        employeeFullNames.append(fullName)

            cur.close()
            employeeFullNames.sort(key=str.lower)
            return employeeFullNames

        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def employeeObjectsInShift(self, shiftid):
        try:
            # create a cursor
            cur = self._conn.cursor()

            # Check if shiftid exists
            QUERY_STRING = 'SELECT shift_id FROM shift_info WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            row = cur.fetchone()
            if row is None:
                print('Shift does not exist.')
                cur.close()
                return False

            # Get all employee netids working in the shift
            QUERY_STRING = 'SELECT netid FROM shift_assign WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            employeeNetids = []
            rows = cur.fetchall()
            if rows is not None:
                for row in rows:
                    netid = row[0]
                    if netid not in employeeNetids:
                        employeeNetids.append(netid)

            # Subtract employees that are added through walk on
            QUERY_STRING = 'SELECT netid FROM walkons WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            rows = cur.fetchall()
            if rows is not None:
                for row in rows:
                    netidRemove = row[0]
                    if netidRemove in employeeNetids:
                        employeeNetids.remove(netidRemove)

            # Get all employee objects working in the shift
            employeeObjects = []
            for netid in employeeNetids:
                QUERY_STRING = 'SELECT * FROM employees WHERE netid = %s'
                cur.execute(QUERY_STRING, (netid,))

                row = cur.fetchone()
                if row is not None:
                    employee = Employee(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10])
                    if employee not in employeeObjects:
                        employeeObjects.append(employee)

            cur.close()
            employeeLObjectsSorted = sorted(employeeObjects, key=lambda x: x._first_name.lower())
            return employeeLObjectsSorted

        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def numberOfEmployeesInShift(self, shiftid):

        try:
            # create a cursor
            cur = self._conn.cursor()

            # Check if shiftid exists
            QUERY_STRING = 'SELECT cur_people FROM shift_info WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            row = cur.fetchone()
            if row is None:
                print('Shift does not exist.')
                cur.close()
                return False
            else:
                cur.close()
                return row[0]

        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def isCoordinator(self, netid):
        try:
            # create a cursor
            cur = self._conn.cursor()

            # Check if coordinator
            QUERY_STRING = 'SELECT netid FROM coordinators WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))

            row = cur.fetchone()
            if row is None:
                print('Not a coordinator')
                cur.close()
                return False
            else:
                return True

        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def isEmployee(self, netid):
        try:
            # create a cursor
            cur = self._conn.cursor()

            # Check if employee
            QUERY_STRING = 'SELECT netid FROM employees WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))

            row = cur.fetchone()
            if row is None:
                print('Not an employee')
                cur.close()
                return False
            else:
                return True

        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def getAllEmails(self):
        try:
            #create a cursor
            cur = self._conn.cursor()
            QUERY_STRING = 'SELECT email FROM employees'
            cur.execute(QUERY_STRING, ())

            emailList = []
            rows = cur.fetchall()
            if rows is not None:
                for row in rows:
                    emailList.append(row[0])
            cur.close()
            return emailList

        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def exportEmployeeData(self):
        try:
            #create a cursor
            cur = self._conn.cursor()
            QUERY_STRING = 'SELECT * FROM employees'

            data = pd.read_sql_query(QUERY_STRING, self._conn)
            writer = pd.ExcelWriter('Dining_Hall_Employees.xlsx')
            data.to_excel(writer, sheet_name='employees')
            writer.save()
            return True

        except (Exception, psycopg2.DatabaseError) as error:
            cur.close()
            print(error)
            return False

    #-----------------------------------------------------------------------

    def addWalkOn(self, shiftid, netid):
        try:
            #create a cursor
            cur = self._conn.cursor()

            # Make sure that walk on is from a past date
            QUERY_STRING = 'SELECT date FROM shift_info WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))
            row = cur.fetchone()

            dateObj = datetime.date.fromisoformat(str(row[0]))

            if dateObj >= datetime.date.today():
                print('This is a future date')
                cur.close()
                return "future"

            # Check if netid exists
            QUERY_STRING = 'SELECT netid FROM employees WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))

            row = cur.fetchone()
            if row is None:
                print('Employee does not exist.')
                cur.close()
                return "not_employee"

            # Check if shiftid exists
            QUERY_STRING = 'SELECT shift_id FROM shift_info WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            row = cur.fetchone()
            if row is None:
                print('Shift does not exist.')
                cur.close()
                return False

            # Check if netid-shiftid is already in shift_assign
            QUERY_STRING = 'SELECT * FROM shift_assign where shift_id=%s AND netid=%s'
            cur.execute(QUERY_STRING, (shiftid, netid))
            row = cur.fetchone()
            if row is not None:
                print('Netid is already working at this shift')
                cur.close()
                return "already_assigned"

            # Insert walkon into walkons table
            QUERY_STRING = 'INSERT INTO walkons(netid, shift_id) VALUES (%s, %s)'
            cur.execute(QUERY_STRING, (netid, shiftid))
            self._conn.commit()
            print('Added walk-on: ' + netid + ' ' + str(shiftid))

            # Increment netid's walkons by 1
            QUERY_STRING = 'UPDATE employees SET walkons = walkons + 1 WHERE netid=%s'
            cur.execute(QUERY_STRING, (netid,))
            self._conn.commit()

            # Add to shift_assign table
            QUERY_STRING = 'INSERT INTO shift_assign(shift_id, netid) VALUES (%s, %s)'
            cur.execute(QUERY_STRING, (shiftid, netid))
            self._conn.commit()
            print('Added walk-on to shift_assign')

            print('Walk-on is committed.')
            cur.close()
            return True

        except (Exception, psycopg2.DatabaseError) as error:
            self._conn.rollback()
            print('Walk-on rolled back.')
            print(error)
            return False

    #-----------------------------------------------------------------------

    def addNoShow(self, shiftid, netid):
        try:
            #create a cursor
            cur = self._conn.cursor()

            # Make sure that no show is from a past date
            QUERY_STRING = 'SELECT date FROM shift_info WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))
            row = cur.fetchone()

            dateObj = datetime.date.fromisoformat(str(row[0]))

            if dateObj >= datetime.date.today():
                print('This is a future date')
                cur.close()
                return "future"

            # Check if netid exists
            QUERY_STRING = 'SELECT netid FROM employees WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))

            row = cur.fetchone()
            if row is None:
                print('Employee does not exist.')
                cur.close()
                return False

            # Check if shiftid exists
            QUERY_STRING = 'SELECT shift_id FROM shift_info WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            row = cur.fetchone()
            if row is None:
                print('Shift does not exist.')
                cur.close()
                return False

            # Check if netid is already on noshow table for this shift
            QUERY_STRING = 'SELECT * FROM noshows where shift_id=%s AND netid=%s'
            cur.execute(QUERY_STRING, (shiftid, netid))
            row = cur.fetchone()
            if row is not None:
                print('Netid is already added as a no-show for this shift')
                cur.close()
                return False

            # Insert noshow into noshows table
            QUERY_STRING = 'INSERT INTO noshows(netid, shift_id) VALUES (%s, %s)'
            cur.execute(QUERY_STRING, (netid, shiftid))
            self._conn.commit()
            print('Added no-show: ' + netid + ' ' + str(shiftid))

            # Increment netid's noshows by 1
            QUERY_STRING = 'UPDATE employees SET noshows = noshows + 1 WHERE netid=%s'
            cur.execute(QUERY_STRING, (netid,))
            self._conn.commit()
            print('Updated noshows number')

            # Remove shift pairing from shift_assign
            QUERY_STRING = 'DELETE FROM shift_assign WHERE netid = %s AND shift_id = %s'
            cur.execute(QUERY_STRING, (netid, shiftid))
            self._conn.commit()
            print('Removed assignment pairing from shift_assign')

            print('No-show is committed.')
            cur.close()
            return True

        except (Exception, psycopg2.DatabaseError) as error:
            self._conn.rollback()
            print('No-show rolled back.')
            print(error)
            return False


    def undoNoShow(self, shiftid, netid):
        try:
            #create a cursor
            cur = self._conn.cursor()

            # Make sure that no show is from a past date
            QUERY_STRING = 'SELECT date FROM shift_info WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))
            row = cur.fetchone()

            dateObj = datetime.date.fromisoformat(str(row[0]))

            if dateObj >= datetime.date.today():
                print('This is a future date')
                cur.close()
                return "future"


            # Check if netid is on the noshow table for this shift
            QUERY_STRING = 'SELECT * FROM noshows where shift_id=%s AND netid=%s'
            cur.execute(QUERY_STRING, (shiftid, netid))
            row = cur.fetchone()
            if row is None:
                print('Noshow pairing does not exist')
                cur.close()
                return False

            # Remove noshow from noshows table
            QUERY_STRING = 'DELETE FROM noshows WHERE netid = %s AND shift_id = %s'
            cur.execute(QUERY_STRING, (netid, shiftid))
            self._conn.commit()
            print('Removed no-show: ' + netid + ' ' + str(shiftid))

            # Decrement netid's noshows by 1
            QUERY_STRING = 'UPDATE employees SET noshows = noshows - 1 WHERE netid=%s AND noshows > 0'
            cur.execute(QUERY_STRING, (netid,))
            self._conn.commit()
            print('Updated noshows number')

            # Insert shift pairing into shift_assign
            QUERY_STRING = 'INSERT INTO shift_assign(shift_id, netid) VALUES (%s, %s)'
            cur.execute(QUERY_STRING, (shiftid, netid))
            self._conn.commit()
            print('Added assignment pairing to shift_assign')

            print('Undo no-show is committed.')
            cur.close()
            return True

        except (Exception, psycopg2.DatabaseError) as error:
            self._conn.rollback()
            print('No-show removal rolled back.')
            print(error)
            return False

    #-----------------------------------------------------------------------

    def noShowsInShift(self, shiftid):
        try:
            # create a cursor
            cur = self._conn.cursor()

            # Check if shiftid exists
            QUERY_STRING = 'SELECT shift_id FROM shift_info WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            row = cur.fetchone()
            if row is None:
                print('Shift does not exist.')
                cur.close()
                return False

            # Get all employee netids in the noshows table
            QUERY_STRING = 'SELECT netid FROM noshows WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            employeeNetids = []
            rows = cur.fetchall()
            if rows is not None:
                for row in rows:
                    netid = row[0]
                    if netid not in employeeNetids:
                        employeeNetids.append(netid)

            # Get all employee full names that didn't show up
            employeeObjects = []
            for netid in employeeNetids:
                QUERY_STRING = 'SELECT * FROM employees WHERE netid = %s'
                cur.execute(QUERY_STRING, (netid,))

                row = cur.fetchone()
                if row is not None:
                    employee = Employee(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10])
                    if employee not in employeeObjects:
                        employeeObjects.append(employee)

            cur.close()
            employeeLObjectsSorted = sorted(employeeObjects, key=lambda x: x._first_name)
            return employeeLObjectsSorted

        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def walkOnsInShift(self, shiftid):
        try:
            # create a cursor
            cur = self._conn.cursor()

            # Check if shiftid exists
            QUERY_STRING = 'SELECT shift_id FROM shift_info WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            row = cur.fetchone()
            if row is None:
                print('Shift does not exist.')
                cur.close()
                return False

            # Get all employee netids in the walkons table
            QUERY_STRING = 'SELECT netid FROM walkons WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            employeeNetids = []
            rows = cur.fetchall()
            if rows is not None:
                for row in rows:
                    netid = row[0]
                    if netid not in employeeNetids:
                        employeeNetids.append(netid)

            # Get all employee full names that walked on
            employeeObjects = []
            for netid in employeeNetids:
                QUERY_STRING = 'SELECT * FROM employees WHERE netid = %s'
                cur.execute(QUERY_STRING, (netid,))

                row = cur.fetchone()
                if row is not None:
                    employee = Employee(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10])
                    if employee not in employeeObjects:
                        employeeObjects.append(employee)

            cur.close()
            employeeLObjectsSorted = sorted(employeeObjects, key=lambda x: x._first_name)
            return employeeLObjectsSorted

        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def getEmployeeObject(self, netid):
        try:
            # create a cursor
            cur = self._conn.cursor()

            # Check if netid exists
            QUERY_STRING = 'SELECT netid FROM employees WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))
            row = cur.fetchone()
            if row is None:
                print('Employee does not exist.')
                cur.close()
                return False

            # Construct employee object
            QUERY_STRING = 'SELECT * FROM employees WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))
            row = cur.fetchone()
            if row is not None:
                employeeObj = Employee(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10])
            cur.close()
            return employeeObj

        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def getTaskHours(self, taskid):

        if (taskid > 13 or taskid < 1):
            print("Taskid must be an integer between 1 and 13")
            return False

        try:
            #create a cursor
            cur = self._conn.cursor()

            QUERY_STRING = 'SELECT start_time, end_time FROM task_info WHERE task_id = %s'
            cur.execute(QUERY_STRING, (taskid,))

            row = cur.fetchone()
            if row is None:
                print('Something went wrong.')
                cur.close()
                return False

            #time_delta = timedelta(row[0])
            #can't just subtract time so we need to add in a common date
            hours = datetime.datetime.combine(datetime.date.today(), row[1]) - datetime.datetime.combine(datetime.date.today(), row[0])
            # print('Subtracted ' + str(row[0]) + ' from ' + str(row[1]) + ' to get a shift time of ' + str(hours))
            cur.close()

            h, m, s = str(hours).split(':')
            numOfHours = float(h) + float(m)/60
            return numOfHours

        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------
    def getShiftHours(self, shiftid):
        try:
            # create a cursor
            cur = self._conn.cursor()

            # Get task id
            QUERY_STRING = 'SELECT task_id FROM shift_info WHERE shift_id = %s'
            cur.execute(QUERY_STRING, (shiftid,))

            row = cur.fetchone()
            if row is None:
                print('Shift does not exist.')
                cur.close()
                return False

            taskid = row[0]

            return self.getTaskHours(taskid)

        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def _hoursEmployee(self, netid, dateStart, dateEnd):
        try:
            #create a cursor
            cur = self._conn.cursor()

            # Check if netid exists
            QUERY_STRING = 'SELECT netid FROM employees WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))

            row = cur.fetchone()
            if row is None:
                print('Employee does not exist.')
                cur.close()
                return False

            # get dates
            if dateStart == -1 and dateEnd == -1:
                today = datetime.date.today()

                QUERY_STRING = 'SELECT cur_pay_period_start FROM payperiod'
                cur.execute(QUERY_STRING)
                row = cur.fetchone()

                if row is None:
                    print('Payperiod missing in database.')
                    cur.close()
                    return False

                curPayPeriodStart = datetime.date.fromisoformat(str(row[0]))
                print(curPayPeriodStart.isoformat())
                if curPayPeriodStart.weekday() != 0:
                    print('Payperiod end date is not a monday.')
                    cur.close()
                    return False

                while today > (curPayPeriodStart + datetime.timedelta(weeks=2)):
                    curPayPeriodStart += datetime.timedelta(weeks=2)
                    QUERY_STRING = 'UPDATE payperiod SET cur_pay_period_start = %s'
                    cur.execute(QUERY_STRING, (curPayPeriodStart.isoformat(),))
                    self._conn.commit()
                    print("Updated current pay period start date: " + curPayPeriodStart.isoformat())

                start = curPayPeriodStart
                end = today
            else:
                start = datetime.date.fromisoformat(dateStart)
                end = datetime.date.fromisoformat(dateEnd)


            # Get all the shifts between start and end dates
            QUERY_STRING = 'SELECT shift_id FROM shift_assign WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))

            workedShifts = []
            rows = cur.fetchall()
            if rows is not None:
                for row in rows:
                    workedShift = self.shiftFromID(row[0])
                    workedShiftDate = datetime.date.fromisoformat(str(workedShift.getDate()))
                    if workedShiftDate >= start and workedShiftDate < end:
                        if workedShift not in workedShifts:
                            workedShifts.append(workedShift)

            # Calculate accumulated hours for all the shifts
            hours = 0
            for shift in workedShifts:
                hours += self.getShiftHours(shift.getShiftID())

            #  Set employee's hours attr to that number
            QUERY_STRING = 'UPDATE employees SET hours = %s WHERE netid = %s'
            cur.execute(QUERY_STRING, (hours, netid))
            self._conn.commit()
            print("Hours updated for employee: " + netid)
            return True

        except (Exception, psycopg2.DatabaseError) as error:
            self._conn.rollback()
            print('Hour update rolled back.')
            print(error)
            return False

    #-----------------------------------------------------------------------

    def _hoursEmployeeNew(self, netid, dateStart, dateEnd):
        try:
            #create a cursor
            cur = self._conn.cursor()

            ''' Removed for efficiency
            # Check if netid exists
            QUERY_STRING = 'SELECT netid FROM employees WHERE netid = %s'
            cur.execute(QUERY_STRING, (netid,))

            row = cur.fetchone()
            if row is None:
                print('Employee does not exist.')
                cur.close()
                return False
            '''

            # get dates
            if dateStart == -1 and dateEnd == -1:
                today = datetime.date.today()

                QUERY_STRING = 'SELECT cur_pay_period_start FROM payperiod'
                cur.execute(QUERY_STRING)
                row = cur.fetchone()

                if row is None:
                    print('Payperiod missing in database.')
                    cur.close()
                    return False

                curPayPeriodStart = datetime.date.fromisoformat(str(row[0]))
                print(curPayPeriodStart.isoformat())
                if curPayPeriodStart.weekday() != 0:
                    print('Payperiod end date is not a monday.')
                    cur.close()
                    return False

                while today > (curPayPeriodStart + datetime.timedelta(weeks=2)):
                    curPayPeriodStart += datetime.timedelta(weeks=2)
                    QUERY_STRING = 'UPDATE payperiod SET cur_pay_period_start = %s'
                    cur.execute(QUERY_STRING, (curPayPeriodStart.isoformat(),))
                    self._conn.commit()
                    print("Updated current pay period start date: " + curPayPeriodStart.isoformat())

                start = curPayPeriodStart
                end = today
            else:
                start = datetime.date.fromisoformat(dateStart)
                end = datetime.date.fromisoformat(dateEnd)


            # Get all the shifts between start and end dates
            QUERY_STRING = 'SELECT shift_id FROM shift_assign WHERE netid=%s' + \
                            'INTERSECT SELECT shift_id FROM shift_info WHERE shift_info.date >= %s AND shift_info.date < %s'
            cur.execute(QUERY_STRING, (netid, start.isoformat(), end.isoformat()))

            workedShifts = []
            rows = cur.fetchall()
            if rows is not None:
                for row in rows:
                    workedShift = self.shiftFromID(row[0])
                    if workedShift not in workedShifts:
                        workedShifts.append(workedShift)

            # Calculate accumulated hours for all the shifts
            hours = 0
            for shift in workedShifts:
                hours += self.getShiftHours(shift.getShiftID())

            #  Set employee's hours attr to that number
            QUERY_STRING = 'UPDATE employees SET hours = %s WHERE netid = %s'
            cur.execute(QUERY_STRING, (hours, netid))
            self._conn.commit()
            print("Hours updated for employee: " + netid)
            return True

        except (Exception, psycopg2.DatabaseError) as error:
            self._conn.rollback()
            print('Hour update rolled back.')
            print(error)
            return False

    #-----------------------------------------------------------------------

    def hoursForAllEmployees(self, dateStart, dateEnd):
        try:
            allEmployees = self.getAllEmployees()

            for employee in allEmployees:
                if not self._hoursEmployeeNew(employee.getNetID(), dateStart, dateEnd):
                    return False

            allEmployees = self.getAllEmployees()
            return allEmployees

        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def hoursForEmployee(self, netid):
        try:
            self._hoursEmployeeNew(netid, -1, -1)

            return True

        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            return False

    #-----------------------------------------------------------------------

    def resetStatsForEmployees(self):
        try:
            #create a cursor
            cur = self._conn.cursor()

            QUERY_STRING = 'UPDATE employees SET subins=0, subouts=0, walkons=0, noshows=0'
            cur.execute(QUERY_STRING)
            self._conn.commit()
            print("Reset subins/subouts/walkons/noshows for all employees")
            cur.close()
            return True

        except (Exception, psycopg2.DatabaseError) as error:
            self._conn.rollback()
            print(error)
            return False

# -----------------------------------------------------------------------

# For testing:

if __name__ == '__main__':
    database = Database()
    database.connect()

    '''
    # Test shiftDetails ***** WORKS
    date = "2020-03-23"
    task_id = 1
    shift = database.shiftDetails(date, task_id)
    print(shift)

    # Test subOut ***** WORKS
    netid_out = 'trt2'
    sub_in_success = database.subOut(netid_out, date, task_id)
    print(sub_in_success)

    # Test subIn ***** WORKS
    netid_in = 'ortaoglu'
    netid_out = 'trt2'
    sub_out_success = database.subIn(netid_in, date, task_id, netid_out)
    print(sub_out_success)

    # Test allSubNeeded ***** WORKS
    subNeededShifts = database.allSubNeeded()
    print()
    print('All Sub Needed Shifts: ')
    for shift in subNeededShifts:
        print(shift)

    # Test allSubsForDate ***** WORKS
    subNeededShiftsForDate = database.allSubsForDate(date)
    print()
    print('All Sub Needed Shifts for 2020-03-23: ')
    for shift in subNeededShiftsForDate:
        print(shift)

    # Test allSubsForWeek ***** WORKS
    date = "2020-03-23"
    print(database.allSubsForWeek(date))

    # Test regularShifts ***** WORKS
    netid = 'yujl'
    regShifts = database.regularShifts(netid)
    print()
    print('Regular shifts for yujl: ')
    for regShift in regShifts:
        print(regShift)

    # Test populateShiftInfo ***** WORKS
    date = "2020-04-27"
    boo = database.populateShiftInfo(date)

    # Test insertEmployee ***** WORKS
    database.insertEmployee('testguy', 'test', 'guy', 'N')

    # Test addRegularShift ***** WORKS
    database.addRegularShift('testguy', 13, 'friday')

    # Test removeRegularShift ***** WORKS
    database.removeRegularShift('testguy', 13, 'friday')
    regShifts = database.regularShifts('testguy')
    print()
    print('Regular shifts for testguy: ')
    #should be none
    for regShift in regShifts:
        print(regShift)

    # Test employeeDetails ***** WORKS
    employee = database.employeeDetails('testguy')
    print(employee.getFirstName() + ' ' + employee.getLastName() + ' ' + employee.getPosition()
          + ' ' + employee.getHours() + ' ' + employee.getTotalHours() + ' ' + employee.getEmail())

    # Test getAllEmployees ***** WORKS
    employees = database.getAllEmployees()
    for indEmployee in employees:
        print(str(indEmployee))

    # Test removeEmployee ***** WORKS
    database.removeEmployee('testguy')

    # Test assignShift ***** WORKS
    database.unassignShift('agurgen', 440)

    # Test employeesInShift ***** WORKS
    myEmployees = database.employeesInShift(494)
    print(myEmployees)

    # Test isCoordinator ***** WORKS
    print(database.isCoordinator('agurgen'))

    # Test isEmployee ***** WORKS
    print(database.isEmployee('agurgen'))

    # Test numberOfEmployeesInShift ***** WORKS
    print(database.numberOfEmployeesInShift(494))

    # Test getAllEmails ***** WORKS
    print(database.getAllEmails())

    # Test exportEmployeeData ***** WORKS
    database.exportEmployeeData()

    # Test addWalkOn ***** WORKS
    database.addWalkOn(440, 'agurgen')

    # Test employeeObjectsInShift
    employees = database.employeeObjectsInShift(400)
    for employee in employees:
        print(employee.getNetID())

    # Test noShowsinShift ***** WORKS
    noShows = database.noShowsInShift(407)
    for employee in noShows:
        print(employee.getNetID())

    # Test walkOnsinShift ***** WORKS
    noShows = database.walkOnsInShift(440)
    for employee in noShows:
        print(employee.getNetID())

    # Test getEmployeeObject ***** WORKS
    empObj = database.getEmployeeObject('trt2')
    print(empObj.getFirstName())

    # Test getTaskHours ***** WORKS
    print(str(database.getTaskHours(1)))

    # Test getShiftHours ***** WORKS
    print(database.getShiftHours(400))

    # Test _hoursEmployee and hoursForEmployee ***** WORKS
    database._hoursForEmployee('trt2', -1, -1)
    print(database.getShiftHours(406) + database.getShiftHours(407) + database.getShiftHours(408) + database.getShiftHours(412) + database.getShiftHours(413) + database.getShiftHours(416) + database.getShiftHours(398))

    database.hoursForEmployee('yap')
    print(database.getTaskHours(1) + database.getTaskHours(3))

    # Test hoursForAllEmployees ***** WORKS
    database.hoursForAllEmployees('2020-04-20', '2020-04-25')

    # Test _checkTaskConflicts ***** WORKS
    print(database._checkTaskConflicts(1, [2, 3]))
    print(database._checkTaskConflicts(2, [3]))

    # Test assignShift after conflict checking ***** WORKS
    print(database.assignShift('agurgen', 568))

    # Test populateForPeriod ***** WORKS
    start = "2020-04-27"
    end = "2020-05-24"
    print(database.populateForPeriod(start, end))

    # Test addNoShow and undoNoShow ***** WORKS
    database.addNoShow(440, 'agurgen')
    database.undoNoShow(440, 'agurgen')

    # Test resetStatsForEmployees ***** WORKS
    database.resetStatsForEmployees()

    # Test new addWalkOn ***** WORKS
    database.addWalkOn(724, 'agurgen')

    # Test populateForPeriod ***** WORKS
    start = "2020-04-27"
    end = "2020-05-24"
    print(database.populateForPeriod(start, end))
    '''


    database.disconnect()
