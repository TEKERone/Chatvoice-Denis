#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# GPL 3.0
# User module for ahorrin chatbot
# Eduardo Contreras Chavez - Francisco Ruben Frias Valderrama
# Verano de investigacion AMC 2018 - Delfin 2018 
# IIMAS-UNAM Dr. Ivan Vladimir Meza Ruiz

def yesno(msg,*args):
    if msg in ['si','sí']:
        return True
    else:
        return False

def number(msg,*args):
    return float(msg)

def list(msg,*args):
    return msg.split()

def asign(msg,*args):
    print(*args)
    for k_a in  args:
        k,a = k_a.split(':',1)
        if msg.find(k)>=0:
            return a
    return 'None'
