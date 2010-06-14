#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright © 2010 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
# Red Hat trademarks are not licensed under GPLv2. No permission is
# granted to use or replicate Red Hat trademarks that are incorporated
# in this software or its documentation.

__author__ = 'Jason L Connor <jconnor@redhat.com>'

import itertools
import threading

# base task queue -------------------------------------------------------------

class TaskQueue(object):
    """
    Abstract base class for task queues for interface definition and typing.
    """
    
    # private methods: storage operations
    
    def _waiting_task(self, task):
        """
        Add a task to the queue's waiting tasks
        @type task: pulp.tasks.task.Task
        @param task: Task instance
        """
        raise NotImplementedError()
        
    def _running_task(self, task):
        """
        Remove a task from the queue's waiting tasks and add it to its running tasks
        @type task: pulp.tasks.task.Task
        @param task: Task instance
        """
        raise NotImplementedError()
        
    def _complete_task(self, task):
        """
        Remove a task from the queue's running tasks and add it to it complete tasks
        @type task: pulp.tasks.task.Task
        @param task: Task instance
        """
        raise NotImplementedError()
    
    def _remove_task(self, task):
        """
        Remove a task from the queue completely
        @type task: pulp.tasks.task.Task
        @param task: Task instance
        """
        raise NotImplementedError()
    
    def _all_tasks(self):
        """
        Get and iterator of all tasks in the queue
        @return: iterator of Task instances
        """
        raise NotImplementedError()
    
    # public methods: queue operations
    
    def enqueue(self, task):
        """
        Add a task to the task queue
        @type task: pulp.tasks.task.Task
        @param task: Task instance
        """
        raise NotImplementedError()
    
    def run(self, task):
        """
        Run a task from this task queue
        @type task: pulp.tasks.task.Task
        @param task: Task instance
        """
        raise NotImplementedError()
    
    def complete(self, task):
        """
        Mark a task run as completed
        @type task: pulp.tasks.task.Task
        @param task: Task instance
        """
        raise NotImplementedError()
    
    def find(self, task_id):
        """
        Find a task in this task queue
        @type task_id: str
        @param task_id: task id
        @return: Task instance on success, None otherwise
        """
        raise NotImplementedError()
    
# no-frills task queue --------------------------------------------------------
    
class SimpleTaskQueue(TaskQueue):
    """
    Derived task queue that provides no special functionality
    """
    def enqueue(self, task):
        task.waiting()
    
    def run(self, task):
        task.run()
    
    def complete(self, task):
        pass
    
    def find(self, task_id):
        return None
    
# base scheduling task queue --------------------------------------------------
    
class SchedulingTaskQueue(TaskQueue):
    """
    Base task queue that dispatches threads to run tasks based on a scheduler.
    """
    def __init__(self, dispatcher_timeout=0.5):
        """
        @type dispatcher_timeout: float
        @param dispatcher_timeout: the max number of seconds before the
                                   dispatcher wakes up to run tasks
        """
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        
        self._waiting_tasks = []
        self._running_tasks = []
        self._complete_tasks = []
        
        self._dispatcher = threading.Thread(target=self._dispatch)
        self._dispatcher.daemon = True
        self._dispatcher.start()
        self._dipatcher_timeout = dispatcher_timeout
        
    # private methods: scheduling
        
    def _dispatch(self):
        """
        Scheduling method that that executes the scheduling hooks
        This should not be overridden by a derived class
        """
        self._lock.acquire()
        while True:
            self._condition.wait(self._dipatcher_timeout)
            self._initial_runs()
            for task in self._get_tasks():
                self._pre_run(task)
                self._run(task)
                self._post_run(task)
            self._finalize_runs()
                
    def _initialize_runs(self):
        """
        Pre-task runs hook that may be overridden in a derived class
        """
        pass
    
    def _finalize_runs(self):
        """
        Post-task runs hook that may be overridden in a derived class
        """
        pass
    
    def _get_tasks(self):
        """
        Scheduling method that retrieve the tasks to be run on on a 
        @return: iterator of Task instances
        """
        raise NotImplementedError()
    
    def _pre_run(self):
        """
        Pre-individual task run hook that may be overridden in a derived class
        """
        pass
    
    def _post_run(self):
        """
        Post-individual task run hook that may be overridden in a derived class
        """
        pass
    
    # public methods: queue operations
    
    def enqueue(self, task):
        self._lock.acquire()
        try:
            task.queue = self
            task.waiting()
            self._waiting_task(task)
        finally:
            self._lock.release()
    
    def run(self, task):
        self._lock.acquire()
        try:
            self._running_task(task)
            thread = threading.Thread(target=task.run)
            thread.start()
        finally:
            self._lock.release()
    
    def complete(self, task):
        self._lock.acquire()
        try:
            self._complete_task(task)
        finally:
            self._lock.release()
    
    def find(self, task_id):
        self._lock.aqcuire()
        try:
            for task in self._all_tasks():
                if task.id == task_id:
                    return task
            return None
        finally:
            self._lock.release()
            
# base memory-resident task queue ---------------------------------------------

class VolatileTaskQueue(TaskQueue):
    """
    Task queue that stores tasks in memory.
    """
    def __init__(self):
        self._waiting_tasks = []
        self._running_tasks = []
        self._complete_tasks = []
        
    def _waiting_task(self, task):
        self._waiting_tasks.append(task)
        
    def _running_task(self, task):
        self._waiting_tasks.remove(task)
        self._running_tasks.append(task)
        
    def _complete_task(self, task):
        self._running_tasks.remove(task)
        self._complete_tasks.append(task)
        
    def _remove_task(self, task):
        if task in self._waiting_tasks:
            self._waiting_tasks.remove(task)
        if task in self._running_tasks:
            self._running_tasks.remove(task)
        if task in self._complete_tasks:
            self._complete_tasks.remove(task)
            
    def _all_tasks(self):
        return itertools.chain(self._waiting_tasks,
                               self._running_tasks,
                               self._complete_tasks)
    
# base database-resident task queue -------------------------------------------

class PersistentTaskQueue(TaskQueue):
    """
    Task queue that stores tasks in a database.
    """
    def __init__(self, db):
        self._db = db
        
    def _waiting_task(self, task):
        raise NotImplementedError()
    
    def _running_task(self, task):
        raise NotImplementedError()
    
    def _complete_task(self, task):
        raise NotImplementedError()
    
    def _remove_task(self, task):
        raise NotImplementedError()
    
    def _all_tasks(self):
        raise NotImplementedError()