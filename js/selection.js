"use strict";

// Good place to use Set? Check https://jsperf.com/set-has-vs-indexof/3 first!
var inlineNodeNames = {
	// text node
	'#text': true,
	// comment node
	'#comment': true,

	// font style
	'FONT': true,
	'TT': true,
	'I': true,
	'B': true,
	'BIG': true,
	'SMALL': true,
	//deprecated
	'STRIKE': true,
	'S': true,
	'U': true,

	// phrase
	'EM': true,
	'STRONG': true,
	'DFN': true,
	'CODE': true,
	'SAMP': true,
	'KBD': true,
	'VAR': true,
	'CITE': true,
	'ABBR': true,
	'ACRONYM': true,

	// special, not included IMG, OBJECT, BR, SCRIPT, MAP, BDO
	'A': true,
	'Q': true,
	'SUB': true,
	'SUP': true,
	'SPAN': true,
	'WBR': true,

	// ruby
	'RUBY': true,
	'RBC': true,
	'RTC': true,
	'RB': true,
	'RT': true,
	'RP': true
};

function isInline(node) {
	return !!inlineNodeNames[node.nodeName] ||
		// Only check styles for elements.
		// Comments do not have getComputedStyle method
		(node.nodeType == Node.ELEMENT_NODE &&
			window.getComputedStyle(node, null).display.startsWith('inline')
		);
}

function nodeFilter(node) {
	if (node.nodeType === Node.ELEMENT_NODE) {
		if (node.nodeName === 'RP' || node.nodeName === 'RT') return NodeFilter.FILTER_REJECT;
		return NodeFilter.FILTER_SKIP;
	}
	return NodeFilter.FILTER_ACCEPT;
}

function getText(rangeNode, maxLength, forward, outText, outSelectionRange, offset) {
	var string = rangeNode.data || rangeNode.value || "";
	if (forward) {
		offset = offset || 0;
		var endIndex = Math.min(string.length, offset + maxLength);
		outText.push(string.substring(offset, endIndex))
		outSelectionRange.push({
			rangeNode,
			offset,
			endIndex
		});
	} else {
		offset = isNaN(offset) ? string.length : offset;
		var startIndex = Math.max(0, offset - maxLength);
		outText.push(string.substring(startIndex, offset));
		outSelectionRange.push({
			rangeNode,
			offset,
			endIndex: startIndex
		});
	}
	return outText[outText.length - 1].length;
}

// Gets text from a node.
// Returns a string.
// node: a node
// selEnd: the selection end object will be changed as a side effect
// maxLength: the maximum length of returned string
// xpathExpr: an XPath expression, which evaluates to text nodes, will be evaluated
// relative to "node" argument
function getInlineText(node, maxLength, forward, outText, outSelectionRange) {
	if (node.nodeType === Node.COMMENT_NODE || node.nodeName === 'RP' || node.nodeName === 'RT') {
		return 0;
	}

	var partialText, endIndex, offset;
	if (node.nodeType === Node.TEXT_NODE) {
		return getText(node, maxLength, forward, outText, outSelectionRange);
	}

	var treeWalker = document.createTreeWalker(node, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, nodeFilter);
	var currentLength = 0;
	node = forward ? treeWalker.firstChild() : treeWalker.lastChild();
	while (currentLength < maxLength && node !== null) {
		currentLength += getText(node, maxLength - currentLength, forward, outText, outSelectionRange);
		node = forward ? treeWalker.nextNode() : treeWalker.previousNode();
	}

	return currentLength;
}

// Given a node which must not be null,
// returns either the next (previous) sibling or next (previous) sibling of the father or
// next (previous) sibling of the fathers father and so on or null
function getNext(node, forward) {
	var nextNode = forward ? node.nextSibling : node.previousSibling;
	if (nextNode !== null) {
		return isInline(nextNode) ? nextNode : null;
	}

	nextNode = node.parentNode;
	if (nextNode !== null) {
		return isInline(nextNode) ? getNext(nextNode, forward) : null;
	}

	return null;
}

// XPath expression which evaluates to a boolean. If it evaluates to true
// then rikaigu will not start looking for text in this text node.
// Ignore text in RT elements
// https://jsperf.com/xpath-vs-traversal-parent-test
var startElementExpr ='boolean(parent::rp or ancestor::rt)';
var maxWordLength = 13;
function getTextFromRange(rangeNode, offset, forward) {
	var text = [], fullSelectionRange = [];
	if (isInput(rangeNode)) {
		getText(rangeNode, maxWordLength, forward, text, fullSelectionRange, offset);
		return [text[0], fullSelectionRange[0]];
	}

	if (rangeNode.nodeType !== Node.TEXT_NODE)
		return ['', null];

	if (document.evaluate(startElementExpr, rangeNode, null, XPathResult.BOOLEAN_TYPE, null).booleanValue)
		return ['', null];

	var currentLength = getText(rangeNode, maxWordLength, forward, text, fullSelectionRange, offset);
	var nextNode = getNext(rangeNode, forward);
	while (nextNode !== null && currentLength < maxWordLength) {
		currentLength += getInlineText(nextNode, maxWordLength - currentLength, forward, text, fullSelectionRange);
		nextNode = getNext(nextNode, forward);
	}

	if (!forward) {
		text.reverse();
	}

	return [text.join(''), fullSelectionRange];
}

var spacePrefixRegexp = /^\s/;
function extractTextAndSearch(dictOption, rangeNode, rangeOffset) {
	if (!rangeNode) {
		rangeNode = rikaigu.lastShownRangeNode;
		rangeOffset = rikaigu.lastShownRangeOffset;
	}
	if (!rangeNode || !document.body.contains(rangeNode)) {
		return reset();
	}
	var data = rangeNode.data || rangeNode.value;

	var match = data.substring(rangeOffset).match(spacePrefixRegexp);
	if (match !== null) {
		/*
		 * For now match[0].length will always be 1,
		 * but what if one day some wonderspace with
		 * code point > 0xffff will be added to unicode?
		 */
		rangeOffset += match[0].length;
	}

	if (rangeOffset >= data.length) {
		return reset();
	}

	var u = data.codePointAt(rangeOffset);
	if (isNaN(u) ||
		(u != 0x25CB && u < 0x20000 &&
			(u < 0x3001 || u > 0x30FF) &&
			(u < 0x3400 || u > 0x9FFF) &&
			(u < 0xF900 || u > 0xFAFF) &&
			(u < 0xFF10 || u > 0xFF9D))) {
		return reset();
	}

	// Selection end data
	var [text, fullSelectionRange] = getTextFromRange(rangeNode, rangeOffset, true);
	text = text.trim();
	if (!text) return reset();

	var [prefix, prefixSelectionRange] = getTextFromRange(rangeNode, rangeOffset, false);
	var trimmedPrefix = prefix.trim();
	if (prefix.endsWith(trimmedPrefix)) {
		prefix = trimmedPrefix;
	} else {
		prefix = "";
	}

	chrome.runtime.sendMessage({
			"type": "xsearch",
			"text": text,
			"prefix": prefix,
			"screenX": rikaigu.lastPos.screenX,
			"screenY": rikaigu.lastPos.screenY,
			"dictOption": dictOption
		},
		processSearchResult.bind(window, fullSelectionRange, prefixSelectionRange));
}