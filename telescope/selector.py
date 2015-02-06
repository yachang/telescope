#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2014 Measurement Lab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import datetime
import json
import logging
import os
import re

import iptranslation
import utils

class Selector(object):
  """ Represents the data required to select a single dataset from
      the M-Lab data.

  """
  def __init__(self):
    self.start_time = None
    self.duration = None
    self.metric = None
    self.ip_translation_spec = None
    self.client_provider = None
    self.site_name = None
    self.mlab_project = None

  def __repr__(self):
    """Return a string description of the selector including such information
       as the duration of the request.

    """

    return "<Selector Object (duration: %i)>" % (self.duration)


class SelectorFileParser(object):
  """ Parser for Telescope, the primary mechanism for specification of
      measurement targets.

  """

  """ Not implemented -- 'hop_count': 'paris_traceroute', """

  supported_metrics = { 'hop_count': 'paris_traceroute',
                        'download_throughput': 'ndt',
                        'upload_throughput': 'ndt',
                        'minimum_rtt': 'ndt',
                        'average_rtt': 'ndt',
                        'packet_retransmit_rate': 'ndt'
                      }

  supported_file_format_versions = {'minimum': 1, 'maximum': 3}
  supported_subset_keys = ["start_time", "client_provider", "site"]

  def __init__(self):
    self.logger = logging.getLogger('telescope')

  def parse(self, selector_filepath):
    """ Parses a selector file into one or more Selector objects. Each selector object
        corresponds to one dataset. If the selector file specifies multiple subsets, the
        parser will generate a separate selector object for each subset. If the selector
        file specifies metric:'all', the parser will generate a separate selector object
        for each supported metric.

        Args:
          selector_filepath (str): Path to selector file to parse.

        Returns:
          list: A list of parsed selector objects.
    """
    with open(selector_filepath, 'r') as selector_fileinput:
      return self._parse_file_contents(selector_fileinput.read())

  def _parse_file_contents(self, selector_file_contents):
    selector_input_json = json.loads(selector_file_contents)
    self.validate_selector_input(selector_input_json)

    metrics = []
    if selector_input_json['metric'] == 'all':
      metrics.extend(self.supported_metrics.keys())
    else:
      metrics.append(selector_input_json['metric'])

    selectors = []
    for selector_subset in selector_input_json['subsets']:
      for metric in metrics:
        selector = Selector()
        selector.start_time = self.parse_start_time(selector_subset['start_time'])
        selector.duration = self.parse_duration(selector_input_json['duration'])
        selector.metric = metric
        selector.ip_translation_spec = self.parse_ip_translation(selector_input_json['ip_translation'])
        selector.client_provider = selector_subset['client_provider']
        selector.site_name = selector_subset['site']
        selector.mlab_project = SelectorFileParser.supported_metrics[metric]

        selectors.append(selector)

    return selectors

  def parse_start_time(self, start_time_string):
    """ Parse the signal start time from the expected timestamp format to
        python datetime format. Must be in UTC time.

        Args:
          measurement (str): Timestamp in format YYYY-MM-DDTHH-mm-SS

        Returns:
          datetime: Python datetime for set timestamp string.

    """
    try:
      timestamp = datetime.datetime.strptime(start_time_string, "%Y-%m-%dT%H:%M:%SZ")
      return utils.make_datetime_utc_aware(timestamp)
    except ValueError:
      raise ValueError('UnsupportedSubsetDateFormat')

  def parse_duration(self, duration_string):
    """ Parse the signal duration from the expected timestamp format to
        integer number of seconds.

        Args:
          duration (str): length in human-readable format, must follow number +
            time type format. (d=days, h=hours, m=minutes, s=seconds), e.g. 30d

        Returns:
          int: Number of seconds in specified time period.

    """

    duration_seconds_to_return = int(0)
    duration_string_segments = re.findall("[0-9]+[a-zA-Z]+", duration_string)

    if len(duration_string_segments) > 0:
      for segment in duration_string_segments:
        numerical_amount = int(re.search("[0-9]+", segment).group(0))
        duration_type = re.search("[a-zA-Z]+", segment).group(0)

        if duration_type == "d":
          duration_seconds_to_return += datetime.timedelta(days = numerical_amount).total_seconds()
        elif duration_type == "h":
          duration_seconds_to_return += datetime.timedelta(hours = numerical_amount).total_seconds()
        elif duration_type == "m":
          duration_seconds_to_return += datetime.timedelta(minutes = numerical_amount).total_seconds()
        elif duration_type == "s":
          duration_seconds_to_return += numerical_amount
        else:
          raise ValueError('UnsupportedSelectorDurationType')
    else:
      raise ValueError('UnsupportedSelectorDuration')

    return duration_seconds_to_return

  def parse_ip_translation(self, ip_translation_dict):
    """ Parse the ip_translation field into an IPTranslationStrategySpec object.

        Args:
          ip_translation_dict (dict): An unprocessed dictionary of
          ip_translation data from the input selector file.

        Returns:
          IPTranslationStrategySpec: An IPTranslationStrategySpec, which specifies
          properties of the IP translation strategy according to the selector file.

    """
    try:
      ip_translation_spec = iptranslation.IPTranslationStrategySpec
      ip_translation_spec.strategy_name = ip_translation_dict['strategy']
      ip_translation_spec.params = ip_translation_dict['params']
      return ip_translation_spec
    except KeyError as e:
      raise ValueError('Missing expected field in ip_translation dict: %s' % e.args[0])

  def validate_selector_input(self, selector_dict):
    if not selector_dict.has_key('file_format_version') or \
            selector_dict['file_format_version'] < self.supported_file_format_versions['minimum'] or \
            selector_dict['file_format_version'] > self.supported_file_format_versions['maximum']:
      raise ValueError('UnsupportedSelectorVersion')

    if not selector_dict.has_key('duration'):
      raise ValueError('UnsupportedDuration')

    if not selector_dict.has_key('metric') or \
            (type(selector_dict['metric']) != str and type(selector_dict['metric']) != unicode) or \
            (selector_dict['metric'] not in self.supported_metrics and \
             selector_dict['metric'] != 'all'):
      raise ValueError('UnsupportedMetric')

    """ For now we only support subset specifications with 1 or 2 (isp, site,
        client) tuples
    """
    if len(selector_dict['subsets']) > 2 or len(selector_dict['subsets']) < 1:
        raise ValueError('UnsupportedSubsetSize')

    if not selector_dict.has_key('subsets') or \
            type(selector_dict['subsets']) != list:
      raise ValueError('UnsupportedSubsets')

    for tuple_set in selector_dict['subsets']:
      if sorted(tuple_set.keys()) != sorted(self.supported_subset_keys):
        raise ValueError('UnsupportedSubsetDefinition')

    """ Selectors should contained two control variables and one independendent
        variable
    """
    if len(selector_dict['subsets']) == 2:
      self.find_independent_variable(selector_dict['subsets'])

    return True

  def find_independent_variable(self, subsets):
    """ Parse two (isp, site, timestamp) tuples and return the key of the
        independent variable.

        Args:
          subsets (list): List of length 2 with (isp, site, timestamp) dicts.

        Returns:
          str: name of the key that is different between the two tuples.

    """

    independent_variable = None

    for key in subsets[0].keys():
      if subsets[0][key] != subsets[1][key] and independent_variable is None:
        independent_variable = key
      elif subsets[0][key] != subsets[1][key] and \
          independent_variable is not None:
        raise ValueError('IncomparableSets')

    if independent_variable == None:
      raise Exception('NoIndependentVariable')

    return independent_variable
