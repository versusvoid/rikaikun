#include "api.h"
#include "crf.h"
#include "dictionaries.h"
#include "html_render.h"
#include "utils.h"

#include <locale>
#include <iostream>
#include <cstring>
#include <cassert>

bool rikaigu_set_file(const char* filename, const char* data, uint32_t length)
{
	if (0 == strcmp(filename, "data/model.bin"))
	{
		return crf_init(data, length);
	}
	else if (0 == strcmp(filename, "data/radicals.dat"))
	{
		return render_init(data, length);
	}
	else
	{
		return dictionaries_init(filename, data, length);
	}

}

const char* rikaigu_search(const char* utf8_text, const char* utf8_prefix, int search_mode,
		int32_t* match_symbols_length, int32_t* prefix_symbols_length)
{
	PROFILE
	SearchResult res = search(utf8_text, SearchMode(search_mode));
	*prefix_symbols_length = 0;
	if (utf8_prefix[0] != '\0' && search_mode == DEFAULT_DICT && config.default_dictionary == "words") {
		std::string extended_text = crf_extend(utf8_text, utf8_prefix, prefix_symbols_length);
		if (extended_text.size() > 0)
		{
			SearchResult res2 = search(extended_text.c_str(), SearchMode(search_mode));
			if (res2.max_match_symbols_length - *prefix_symbols_length >= res.max_match_symbols_length)
			{
				res = res2;
			}
			else
			{
				*prefix_symbols_length = 0;
			}
		}
		else
		{
			assert(*prefix_symbols_length == 0);
		}
	}
	*match_symbols_length = int32_t(res.max_match_symbols_length);
	return  make_html(res);
}

const char* rikaigu_translate(const char* utf8_text)
{
	std::string text(utf8_text);
	SearchResult res;
	res.title = text;

        while (text.length() > 0)
	{
		auto partial_res = word_search(text.c_str(), false, 1);
		if (partial_res.max_match_symbols_length > 0)
		{
			if (res.data.size() >= 7)
			{
				res.more = true;
				break;
			}
			res.data.push_back(partial_res.data.at(0));
			text = text.substr(partial_res.data.at(0).match_bytes_length);
		}
		else
		{
			text = text.substr(mbrlen(text.c_str(), text.length(), nullptr));
		}
        }

	if (text.length() > 0)
	{
		res.title.resize(res.title.length() - text.length());
		res.title += "...";
	}
        return make_html(res);
}
