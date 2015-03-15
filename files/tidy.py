#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2014, Ruggero Marchei <ruggero.marchei@daemonzone.net>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>


import os
import fnmatch
import time
import re
import shutil


DOCUMENTATION = '''
---
module: tidy
author: Ruggero Marchei
version_added: "1.8"
short_description: Remove unwanted files based on specific criteria
requirements: []
description:
    - Remove unwanted files based on specific criteria. Multiple criteria are AND'd together. 
options:
    age:
        required: false
        default: "0"
        description:
            - Tidy files whose age is equal to or greater than the specified time. 
              You can choose seconds, minutes, hours, days, or weeks by specifying the first letter of any of those words (e.g., "1w"). 
              Specifying 0 will remove all files.
    force:
        required: false
        default: "no"
        choices: [ "yes", "no" ]
        description:
            - Force removal of non empty directories.
    matches:
        required: false
        description:
            - One or more (shell type) file glob patterns, which restrict the list of files to be tidied to those whose basenames match at least one of the patterns specified. 
              Multiple patterns can be specified using a list.
    path:
        required: true
        aliases: [ "name" ]
        description:
            - Path to the file or directory to manage. Must be fully qualified.
    recurse:
        required: false
        default: "no"
        choices: [ "yes", "no" ]
        description:
            - If target is a directory, recursively descend into the directory looking for files to tidy.
    rmdirs:
        required: false
        default: "no"
        choices: [ "yes", "no" ]
        description:
            - Tidy directories in addition to files; that is, remove directories whose age is older than the specified criteria. 
              This will only remove empty directories, so all contained files must also be tidied before a directory gets removed.
    silent:
        required: false
        default: "no"
        choices: [ "yes", "no" ]
        description:
            - Silently ignore failed commands.
    size:
        required: false
        default: "0"
        description:
            - Tidy files whose size is equal to or greater than the specified size. 
              Unqualified values are in bytes, but b, k, m, g, and t can be appended to specify bytes, kilobytes, megabytes, gigabytes, and terabytes, respectively. 
              Size is not evaluated for directories.
    timestamp:
        required: false
        default: "atime"
        choices: [ "atime", "mtime", "ctime" ]
        description:
            - Set the mechanism for determining age. Default is atime.
'''


EXAMPLES = '''
# Recursively delete on /tmp files older than 2 days
- tidy: path="/tmp" age="2d" recurse=yes

# Recursively delete on /tmp files older than 4 weeks and equal or greater than 1 megabyte
- tidy: path="/tmp" age="4w" size="1m" recurse=yes

# Recursively delete on /var/tmp files and empty directories with last access time greater than 3600 seconds
- tidy: path="/var/tmp" age="3600" timestamp=atime rmdirs=yes recurse=yes

# Delete on /var/log files equal or greater than 10 megabytes ending with .log or .log.gz
- tidy: path="/var/tmp" matches="*.log","*.log.gz" size="10m"
'''


def pfilter(f, pattern=None):
    '''filter using glob patterns'''
    if pattern is None:
        return True
    for p in pattern:
        if fnmatch.fnmatch(f, p):
             return True
    return False
    
    
def agefilter(path, age=0, timestamp="atime"):
    '''filter files older than age'''
    if age == 0 or time.time() - os.stat(path).__getattribute__("st_%s" % timestamp) >= age:
        return True
    return False
        

def sizefilter(path, size=0):
    '''filter files greater than size'''
    if size == 0 or os.stat(path).st_size >= size:
        return True
    return False

                        
def main():
    module = AnsibleModule(
            argument_spec   = dict(
                path        = dict(required=True, aliases=['name'], type='str'),
                age         = dict(default=0, type='str'),
                force       = dict(default='no', type='bool'),
                matches     = dict(default=None, type='list'),
                recurse     = dict(default='no', type='bool'),
                rmdirs      = dict(default='no', type='bool'),
                size        = dict(default=0, type='str'),
                timestamp   = dict(default="atime", choices=['atime','mtime','ctime'], type='str'),
                silent      = dict(default='no', type='bool')
            ),
            supports_check_mode = True
    )

    params = module.params
        
    files_to_delete = []
    dirs_to_delete = []
    
    changed = False
    
    # convert age to seconds:
    m = re.match("^(\d+)(s|m|h|d|w)?$", params['age'].lower())
    seconds_per_unit = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    if m:
        age = int(m.group(1)) * seconds_per_unit.get(m.group(2), 1)
    else:
        module.fail_json(age=params['age'], msg="failed to process age")
        
    
    # convert size to bytes:
    m = re.match("^(\d+)(b|k|m|g|t)?$", params['size'].lower())
    bytes_per_unit = {"b": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
    if m:
        size = int(m.group(1)) * bytes_per_unit.get(m.group(2), 1)
    else:
        module.fail_json(size=params['size'], msg="failed to process size")
    
    
    if os.path.isdir(params['path']):
        for root,dirs,files in os.walk( params['path'] ):
            for fsobj in dirs + files:
                fsname=os.path.normpath(os.path.join(root, fsobj))
                if os.path.isdir(fsname):
                    if pfilter(fsobj, params['matches']) and agefilter(fsname, age, params['timestamp']) and params['rmdirs']:
                        dirs_to_delete.append(fsname)
                elif os.path.isfile(fsname):
                    if pfilter(fsobj, params['matches']) and agefilter(fsname, age, params['timestamp']) and sizefilter(fsname, size):
                        files_to_delete.append(fsname)
            if not params['recurse']: 
                break
    elif os.path.isfile(params['path']):
        fsobj = os.path.basename(params['path'])
        fsname = os.path.normpath(params['path'])
        if pfilter(fsobj, params['matches']) and agefilter(fsname, age, params['timestamp']) and sizefilter(fsname, size):
            files_to_delete.append(fsname)
    
    files_to_delete.sort()
    dirs_to_delete.sort(reverse=not params['force'])
    
    if module.check_mode == True:
        if len(files_to_delete) > 0 or len(dirs_to_delete) > 0:
            changed = True
        module.exit_json(deleted_files=files_to_delete, deleted_dirs=dirs_to_delete, changed=changed)
                 
    deleted_files = []
    deleted_dirs = []
    
    for f in files_to_delete:
        try:
            os.remove(f)
            deleted_files.append(f)
        except Exception, e:
            if params['silent']:
                continue
            module.fail_json(deleted_files=deleted_files, deleted_dirs=deleted_dirs, path=f, msg="failed to process file: %s " % str(e))

    for d in dirs_to_delete:
        if os.path.exists(d):
            try:
                if params['force'] or len(os.listdir(d)) == 0:
                    if os.path.islink(d):
                        os.remove(d)
                    else:
                        shutil.rmtree(d)
                    deleted_dirs.append(d)
            except Exception, e:
                if params['silent']:
                    continue
                module.fail_json(deleted_files=deleted_files, deleted_dirs=deleted_dirs, path=d, msg="failed to process directory: %s " % str(e))
            
    if len(deleted_files) > 0 or len(deleted_dirs) > 0:
        changed = True
    module.exit_json(deleted_files=deleted_files, deleted_dirs=deleted_dirs, changed=changed)
                        
# import module snippets
from ansible.module_utils.basic import *
main()

