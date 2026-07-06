# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from pathlib import Path


def test_form_designer_legacy_suite_is_replaced_by_generic_js_suite():
    assert (Path(__file__).with_name("test_form_designer_generic_js.py")).is_file()
