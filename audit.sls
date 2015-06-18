# Salt state file for zabbixaudit installation.
#

{% set script = '/etc/zabbix/scripts/zabbixaudit' %}

{% set pip = [
    'mysql-connector-python',
    'splunk-sdk',
   ] %}

{% set zabbix = {
    'db': salt['pillar.get']('zabbix:db:name', 'zabbix'),
    'dbhost': salt['pillar.get']('zabbix:db:host', '127.0.0.1'),
    'user': salt['pillar.get']('zabbix:db:user', 'admin'),
    'pass': salt['pillar.get']('zabbix:db:pass', 'zabbix'),
    } %}

{% set splunk = {
    'host': 'salt['pillar.get']('splunk:host', 'localhost'),
    'user': salt['pillar.get']('zabbix:audit:user', 'admin'),
    'pass': salt['pillar.get']('zabbix:audit:pass', 'changeme'),
    'index': salt['pillar.get']('zabbix:audit:index', 'zabbix'),
    } %}

{% set hostname = salt['cmd.run']('hostname', 'localhost') %}

{% for package in pip %}
{{ package }}:
    pip.installed: []
{% endfor %}

zabbixaudit:
  file.managed:
    - name: {{ script }}
    - source: salt://zabbixaudit.py
    - mode: 755
  cron.present:
    - name: {{ script }} --zhost {{ zabbix.dbhost }} --zdb {{ zabbix.db }} --zuser  {{ zabbix.user }} --zpass {{ zabbix.pass }} --host {{ hostname }} --sindex {{ splunk.index }} --suser {{ splunk.user }} --spass {{ splunk.pass }} --shost {{ splunk.host }}
    - user: root
    - minute: '*/1'
    - comment: Send zabbix audit log to splunk
