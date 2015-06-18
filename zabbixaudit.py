#!/usr/bin/env python

import argparse
import logging
import mysql.connector
import splunklib.client as client

class ZabbixAudit(object):
    """ Object wrapper to get audit info from zabbix """

    def __init__(self, zabbixdb_conf, continueFrom):
        self.db = mysql.connector.connect(**zabbixdb_conf)
        self.dbc = self.db.cursor()
        self.sp_name = 'get_audit'
        if not self._is_sp_exist(self.sp_name):
            self._create_sp(self.sp_name)

    def _is_sp_exist(self, name):
        """ Return True if stored procudure exist, otherwise return False """

        self.dbc.nextset()
        self.dbc.execute("show procedure status where NAME='{name}';".format(
            name=name))
        return bool(self.dbc.fetchall())

    def _create_sp(self, name):
        """ Create stored procedure with given name """

        self.dbc.nextset()
        get_audit_sp = """
        CREATE DEFINER=`zabbix`@`%` PROCEDURE `{name}`(IN lastSelect INT)
        BEGIN
                SET lastSelect = IFNULL(lastSelect,0);
                SELECT from_unixtime(`a1`.`clock`, '%Y/%m/%d %h:%i:%s %p PDT'),
                                `u`.`alias`,
                                `a1`.`ip`,
                                CASE `a1`.`action`
                                        WHEN 0 THEN 'add'
                                        WHEN 1 THEN 'update'
                                        WHEN 2 THEN 'delete'
                                        WHEN 3 THEN 'login'
                                        WHEN 4 THEN 'logout'
                                        WHEN 5 THEN 'enable'
                                        WHEN 6 THEN 'disable'
                                END as `action`,
                                CASE `a1`.`resourcetype`
                                        WHEN 0 THEN 'User'
                                        WHEN 11 THEN 'User group'
                                        WHEN 12 THEN 'Application'
                                        WHEN 13 THEN 'Trigger'
                                        WHEN 14 THEN 'Host group'
                                        WHEN 15 THEN 'Item'
                                        WHEN 16 THEN 'Image'
                                        WHEN 17 THEN 'Value map'
                                        WHEN 18 THEN 'IT service'
                                        WHEN 19 THEN 'Map'
                                        WHEN 2 THEN 'Configuration of Zabbix'
                                        WHEN 20 THEN 'Screen'
                                        WHEN 21 THEN 'Node'
                                        WHEN 22 THEN 'Scenario'
                                        WHEN 23 THEN 'Discovery rule'
                                        WHEN 24 THEN 'Slide show'
                                        WHEN 25 THEN 'Script'
                                        WHEN 26 THEN 'Proxy'
                                        WHEN 27 THEN 'Maintenance'
                                        WHEN 28 THEN 'Regular expression'
                                        WHEN 29 THEN 'Macro'
                                        WHEN 3 THEN 'Media type'
                                        WHEN 30 THEN 'Template'
                                        WHEN 31 THEN 'Trigger prototype'
                                        WHEN 4 THEN 'Host'
                                        WHEN 5 THEN 'Action'
                                        WHEN 6 THEN 'Graph'
                                        WHEN 7 THEN 'Graph element'
                                END as `resourcetype`,
                                COALESCE(NULLIF(`a1`.`resourcename`, ''),`a1`.`details`) as `name`,
                                `a2`.`oldvalue`,
                                `a2`.`newvalue`,
                                `a1`.`auditid`
                FROM `auditlog` AS `a1`
                LEFT JOIN `auditlog_details` AS `a2`
                ON `a1`.`auditid`=`a2`.`auditid`
                LEFT JOIN `users` AS `u`
                ON `a1`.`userid`=`u`.`userid`
                WHERE `a1`.`auditid` > lastSelect
                ORDER BY `a1`.`auditid` DESC;
        END;""".format(name=name)
        self.dbc.execute(get_audit_sp)

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self.db.close()

    def read(self):
        """ Return list of tuples with audit records """

        self.dbc.nextset()
        self.dbc.callproc(self.sp_name, [continueFrom])
        result = []
        for res in self.dbc.stored_results():
            result.extend(res.fetchall())
        return result

class SplunkIndex(object):
    """ Object wrapper for write data to splunk index """

    def __init__(self, splunk_conf, splunk_evt, splunk_index):
        self.splunk = client.connect(**splunk_conf)
        if not splunk_index in self.splunk.indexes:
            self.index = self.splunk.indexes.create(splunk_index)
        else:
            self.index = self.splunk.indexes[splunk_index]
        self.socket = self.index.attach(**splunk_evt)

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self.socket.close()

    def write(self, data):
        """ Write data to splunk index, and return last written actionid """

        result = 0
        for row in data:
            text = "date='{0}', account='{1}', ip='{2}', action='{3}', type='{4}', name='{5}'".format(*row)
            if len(row) > 6 and not None in row[6:7]:
                text += ", old='{6}', new='{7}'".format(*row)
            log.info(text)
            text += "\r\n"
            self.socket.send(text)
            result = data[0][len(data[0])-1]
        return result


def loadFromFile(filename):
    """ Helper function: load one integer from file """

    result = 0
    try:
        with open(filename, 'r') as f:
            result = int(f.read())
    except:
        log.info("Can't read file")
    finally:
        return result

def saveToFile(filename, data):
    """ Helper function: save data to file """
    try:
        with open(filename, 'w') as f:
            f.write('{0}'.format(data))
    except:
        log.info("Can't write to file")

def argParser():
    """ Helper function: return parsed arguments """
    argparser = argparse.ArgumentParser()
    argparser.add_argument('--zhost', required=True, help='Zabbbix DB host')
    argparser.add_argument('--zdb', required=True, help='Zabbbix DB name')
    argparser.add_argument('--zuser', required=True, help='Zabbbix DB user')
    argparser.add_argument('--zpass', required=True, help='Zabbbix DB passowrd')
    argparser.add_argument('--shost', required=True, help='Splunk host')
    argparser.add_argument('--sindex', required=True, help='Splunk Index name')
    argparser.add_argument('--suser', required=True, help='Splunk user')
    argparser.add_argument('--spass', required=True, help='Splunk password')
    argparser.add_argument('--host', required=True, help='Name of host will be showed in Splunk')
    argparser.add_argument('--continue', type=int, help='Action ID in zabbix db, to continue from')
    return  vars(argparser.parse_args())

if __name__ == '__main__':

    log = logging.getLogger(__name__)
    logging.basicConfig(
            level=logging.INFO,
            format='[%(asctime)s] %(message)s',
            datefmt='%d/%m/%Y %H:%M:%S')

    # get arguments
    args = argParser()

    zabbixdb_conf = {
            'host': args['zhost'],
            'database': args['zdb'],
            'user': args['zuser'],
            'password': args['zpass'],
    }

    splunk_conf = {
            'host': args['shost'],
            'username': args['suser'],
            'password': args['spass'],
    }

    splunk_evt = {
            'sourcetype': 'zabbix-audit',
            'source': 'zabbix-db',
            'host': args['host'],
    }

    splunk_index = args['sindex']

    # Load actionid from which we should continue work.
    tmpFile = '/tmp/zabbixaudit'
    if 'continue' in args and args['continue'] != None:
        continueFrom = args['continue']
    else:
        continueFrom = loadFromFile(tmpFile)
    log.info('Continue from event %d', continueFrom)

    # Get audit log from zabbix and send it to splunk
    with ZabbixAudit(zabbixdb_conf, continueFrom) as db:
        with SplunkIndex(splunk_conf, splunk_evt, splunk_index) as splunk:
            data = db.read()
            continueFrom = splunk.write(data)
            log.info('%d events was added to splunk index[%s]', len(data), splunk_index)

            if continueFrom:
                # Save last actionid to continue with at next run.
                saveToFile(tmpFile, continueFrom)
