#!/usr/bin/env python3

import re
import struct
import itertools
from collections import defaultdict

import dictionary
import wasm_generator
from utils import kata_to_hira
from index import index_keys
from romaji import is_romajination

control_sense_symbols = re.compile('[\\`]')
def format_sense(sense, entry):
	parts = []
	kanji_restriction = sense.kanji_restriction or ()
	reading_restriction = sense.reading_restriction or ()
	if len(kanji_restriction) + len(reading_restriction) > 0:
		restrictions = []
		for ki in kanji_restriction:
			restrictions.append(entry.kanjis[ki].text)
		for ri in reading_restriction:
			restrictions.append(entry.readings[ri].text)
		parts.append('(only ' + ','.join(restrictions) + ')')

	if bool(sense.s_inf):
		parts.append('(' + sense.s_inf + ')')

	parts.append('; '.join(sense.glosses))

	res = ' '.join(parts)
	assert control_sense_symbols.search(res) is None
	return res

trans_type_abbreviations = {
	"place": "a",
	"company": "c",
	"product": "d",
	"fem": "f",
	"given": "g",
	"masc": "m",
	"surname": "n",
	"organization": "o",
	"person": "p",
	"station": "s",
	"unclass": "u",
	"work": "w",
}
def format_trans(trans, name):
	parts = []
	parts.append(','.join(map(trans_type_abbreviations.__getitem__, trans.types)))
	if (len(trans.glosses) == 1 and len(name.readings) == 1
				and is_romajination(kata_to_hira(name.readings[0].text, agressive=False), trans.glosses[0])):
		pass
	else:
		parts.append(';')
		parts.append('; '.join(trans.glosses))
	return ''.join(parts)

_base62_alphabeth = [
	*map(str, range(ord('0'), ord('9') + 1)),
	*map(str, range(ord('a'), ord('z') + 1)),
	*map(str, range(ord('A'), ord('Z') + 1)),
]
assert len(_base62_alphabeth) == 62
def format_uint_base62(v):
	v, i = divmod(v, 62)
	s = [_base62_alphabeth[i]]
	while v != 0:
		v, i = divmod(v, 62)
		s.append(_base62_alphabeth[i])
	return ''.join(s)

control_kanji_symbols = re.compile('[#|U,;\t]')
control_reading_symbols = re.compile('[|U;\t]')
max_readings_index = 0
def format_entry(entry, min_entry_id=None):
	global max_readings_index

	any_common_kanji = any(map(lambda k: k.common, entry.kanjis))
	any_common_kana = any(map(lambda r: r.common, entry.readings))

	parts = []
	if len(entry.kanjis) > 0:
		'''
		Inverse kanjis-readings restrictions, because we render kanjis first,
		then readings, so kanjis rendered on this line must define which
		readings are going to be rendered after
		'''
		kanji_index_to_readings = {}
		for ri, r in enumerate(entry.readings):
			kanji_indices = r.kanji_restriction or range(len(entry.kanjis))
			for ki in kanji_indices:
				kanji_index_to_readings.setdefault(ki, []).append(ri)

		grouped_readings_to_kanji_offsets = {}
		for ki, reading_indices in kanji_index_to_readings.items():
			grouped_readings_to_kanji_offsets.setdefault(tuple(reading_indices), []).append(ki)
		del kanji_index_to_readings

		'''
		Format kanji groups
		'''
		groups = []
		seen = set()
		for reading_indices, kanji_offsets in grouped_readings_to_kanji_offsets.items():
			for i, ki in enumerate(kanji_offsets):
				seen.add(ki)
				k = entry.kanjis[ki]
				assert control_kanji_symbols.search(k.text) is None
				kanji_offsets[i] = k.text
				if any_common_kanji and not k.common:
					kanji_offsets[i] += 'U'

			groups.append(','.join(kanji_offsets))
			if len(reading_indices) != len(entry.readings):
				max_readings_index = max(max_readings_index, *reading_indices)
				groups[-1] += '#' + ','.join(map(str, reading_indices))

		'''
		Format ungrouped kanjis
		'''
		for ki, k in enumerate(entry.kanjis):
			if ki in seen:
				continue
			assert control_kanji_symbols.search(k.text) is None
			groups.append(k.text)
			if any_common_kanji and not k.common:
				groups[-1] += 'U'

		parts.append(';'.join(groups))
		del seen, groups

	'''
	Format readings
	'''
	readings = []
	for r in entry.readings:
		assert control_reading_symbols.search(r.text) is None
		readings.append(r.text)
		if any_common_kana and not r.common:
			readings[-1] += 'U'
	parts.append(';'.join(readings))
	del readings

	if type(entry) == dictionary.Entry:
		'''
		Format sense groups
		'''
		sense_groups = []
		for g in entry.sense_groups:
			# TODO use mecab to infer additional pos for exp entries
			sense_groups.append(','.join(g.pos) + ';' + '`'.join(map(lambda s: format_sense(s, entry), g.senses)))
		parts.append('\\'.join(sense_groups))
		del sense_groups

		parts.append(format_uint_base62(entry.id - min_entry_id))
	else:
		transes = []
		for t in entry.transes:
			transes.append(format_trans(t, entry))
		parts.append('\\'.join(transes))
		del transes

	return '\t'.join(parts)

def prepare_names():
	index = defaultdict(set)
	offset = 0
	combined_entries = {}
	dictionary_lines = []
	for entry in dictionary.dictionary_reader('JMnedict.xml.gz'):
		if len(entry.readings) == 1 and len(entry.transes) == 1 and len(entry.transes[0].glosses) == 1:
			key = entry.readings[0].text + ' - ' + ','.join(entry.transes[0].types)
			combined_entry = combined_entries.get(key)
			if combined_entry is None:
				combined_entries[key] = entry
			else:
				combined_entry.kanjis.extend(entry.kanjis)
			continue

		entry_index_keys = index_keys(entry, variate=False)
		for key in entry_index_keys:
			index[key].add(offset)

		line = format_entry(entry).encode('utf-8')
		dictionary_lines.append(line)
		offset += len(line) + 1

	for combined_entry in combined_entries.values():
		entry_index_keys = index_keys(combined_entry, variate=False)
		for key in entry_index_keys:
			index[key].add(offset)

		line = format_entry(combined_entry).encode('utf-8')
		dictionary_lines.append(line)
		offset += len(line) + 1

	return dictionary_lines, index

def prepare_words(pos_flags_map):
	min_entry_id = 2**63
	for entry in dictionary.dictionary_reader('JMdict_e.gz'):
		min_entry_id = min(entry.id, min_entry_id)

	index = defaultdict(set)
	offset = 0
	dictionary_lines = []
	for entry in dictionary.dictionary_reader('JMdict_e.gz'):
		all_pos = set(itertools.chain.from_iterable(sg.pos for sg in entry.sense_groups))
		pos_flags = sum(pos_flags_map.get(pos, 0) for pos in all_pos)
		index_entry = offset if pos_flags == 0 else wasm_generator.TypedOffset(type=pos_flags, offset=offset)

		for key in index_keys(entry, variate=True):
			index[key].add(index_entry)

		line = format_entry(entry, min_entry_id).encode('utf-8')
		dictionary_lines.append(line)
		offset += len(line) + 1

	return dictionary_lines, index, min_entry_id

def index_kanji():
	index = []
	offset = 0

	entry_no = 0
	with open('data/kanji.dat', 'r') as f:
		for l in f:
			entry_no += 1
			if entry_no % 1000 == 0:
				print('kanji', entry_no)
			index.append((ord(l[0]), offset))
			offset += len(l.encode('utf-8'))

	index.sort()
	with open('data/kanji.idx', 'wb') as of:
		for kanji_code_point, offset in index:
			of.write(struct.pack('<II', kanji_code_point, offset))

pos_flags_map = wasm_generator.generate_deinflection_rules_header()
words_dictionary, words_index, min_entry_id = prepare_words(pos_flags_map)
names_dictionary, names_index = prepare_names()

wasm_generator.write_dictionaries(words_dictionary, names_dictionary)
wasm_generator.write_utf16_indexies(words_index, names_index)
wasm_generator.generate_config_header(max_readings_index, min_entry_id)
wasm_generator.get_lz4_source()

# TODO generate kanji.dat
index_kanji()
