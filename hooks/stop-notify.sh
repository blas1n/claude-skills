#!/usr/bin/env bash
# Stop hook: send terminal notification when Claude finishes a task
printf '\\ePtmux;\\e\\e]777;notify;Claude Done;Task finished\\a\\e\\\\'
