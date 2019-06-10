# -*- coding: utf-8 -*-
"""
Holds the code for cleaning out unwanted tags from the lxml
dom xpath.
"""
import re
import copy
from .utils import ReplaceSequence


class DocumentCleaner(object):

    def __init__(self, config):
        """Set appropriate tag names and regexes of tags to remove
        from the HTML
        """
        self.config = config
        self.parser = self.config.get_parser()
        self.remove_nodes_re = re.compile(
            "^side$|combx|retweet|mediaarticlerelated|menucontainer|"
            "navbar|storytopbar-bucket|utility-bar|inline-share-tools"
            "|comment|PopularQuestions|contact|foot|footer|Footer|footnote"
            "|cnn_strycaptiontxt|cnn_html_slideshow|cnn_strylftcntnt"
            "|links|meta$|shoutbox|sponsor"
            "|tags|socialnetworking|socialNetworking|cnnStryHghLght"
            "|cnn_stryspcvbx|^inset$|pagetools|post-attributes"
            "|welcome_form|contentTools2|the_answers"
            "|communitypromo|runaroundLeft|subscribe|vcard|articleheadings"
            "|date(?!-posts|-outer)"  # blogspot.com rules
            "|^print$|popup|author-dropdown|tools|socialtools|byline"
            "|konafilter|KonaFilter|breadcrumbs|^fn$|wp-caption-text"
            "|legende|ajoutVideo|timestamp|js_replies",
            re.I
        )
        self.regexp_namespace = "http://exslt.org/regular-expressions"
        self.div_to_p_re = r"<(a|blockquote|dl|div|img|ol|p|pre|table|ul)"
        self.remove_re = re.compile("^caption$| google |^[^entry-]more.*$|[^-]facebook"
                                    "|facebook-broadcasting|[^-]twitter", re.I)

        self.tablines_replacements = ReplaceSequence()\
            .create("\n", "\n\n")\
            .append("\t")\
            .append("^\\s+$")
        self.contains_article = './/article|.//*[@id="article"]|.//*[@itemprop="articleBody"]'
        self.article_nodes_re = re.compile('article|StoryBody|post-body', re.I)

    def clean(self, doc_to_clean):
        """Remove chunks of the DOM as specified
        """
        doc_to_clean = self.clean_body_classes(doc_to_clean)
        doc_to_clean = self.clean_article_tags(doc_to_clean)
        doc_to_clean = self.clean_em_tags(doc_to_clean)
        doc_to_clean = self.remove_drop_caps(doc_to_clean)

        naughty_list = []
        for node in doc_to_clean.iter():
            if (self.is_script_style_comment(node)
                    or self.clean_bad_tags(node)
                    or self.remove_nodes_regex(node)):
                naughty_list.append(node)
        for node in naughty_list:
            self.parser.remove(node)

        doc_to_clean = self.clean_para_spans(doc_to_clean)
        doc_to_clean = self.article_to_para(doc_to_clean)
        doc_to_clean = self.div_to_para(doc_to_clean, ['div', 'span', 'section'])
        return doc_to_clean

    def clean_body_classes(self, doc):
        """Removes the `class` attribute from the <body> tag because
        if there is a bad match, the entire DOM will be empty!
        """
        elements = self.parser.getElementsByTag(doc, tag="body")
        if elements:
            self.parser.delAttribute(elements[0], attr="class")
        return doc

    def clean_article_tags(self, doc):
        articles = self.parser.getElementsByTag(doc, tag='article')
        for article in articles:
            for attr in ['id', 'name', 'class']:
                self.parser.delAttribute(article, attr=attr)
        return doc

    def clean_em_tags(self, doc):
        ems = self.parser.getElementsByTag(doc, tag='em')
        for node in ems:
            images = self.parser.getElementsByTag(node, tag='img')
            if len(images) == 0:
                self.parser.drop_tag(node)
        return doc

    def remove_drop_caps(self, doc):
        items = self.parser.css_select(doc, 'span[class~=dropcap], '
                                       'span[class~=drop_cap]')
        for item in items:
            self.parser.drop_tag(item)
        return doc

    def is_script_style_comment(self, node):
        return self.parser.getTag(node) in ('script', 'style') or self.parser.isComment(node)

    def clean_bad_tags(self, node):
        for selector in ['id', 'class', 'name']:
            value = node.attrib.get(selector) or ''
            if self.remove_nodes_re.search(value) and not node.xpath(self.contains_article):
                return True
        return False

    def remove_nodes_regex(self, node):
        for selector in ['id', 'class']:
            value = node.attrib.get(selector) or ''
            if self.remove_re.search(value):
                return True
        return False

    def clean_para_spans(self, doc):
        spans = self.parser.css_select(doc, 'p span')
        for item in spans:
            self.parser.drop_tag(item)
        return doc

    def get_flushed_buffer(self, replacement_text, doc):
        return self.parser.textToPara(replacement_text)

    def replace_walk_left_right(self, kid, kid_text,
                                replacement_text, nodes_to_remove):
        kid_text_node = kid
        replace_text = self.tablines_replacements.replaceAll(kid_text)
        if len(replace_text) > 1:
            prev_node = self.parser.previousSibling(kid_text_node)
            while prev_node is not None \
                    and self.parser.getTag(prev_node) == "a" \
                    and self.parser.getAttribute(
                        prev_node, 'grv-usedalready') != 'yes':
                outer = " " + self.parser.outerHtml(prev_node) + " "
                replacement_text.append(outer)
                nodes_to_remove.append(prev_node)
                self.parser.setAttribute(prev_node, attr='grv-usedalready',
                                         value='yes')
                prev_node = self.parser.previousSibling(prev_node)

            replacement_text.append(replace_text)
            next_node = self.parser.nextSibling(kid_text_node)
            while next_node is not None \
                    and self.parser.getTag(next_node) == "a" \
                    and self.parser.getAttribute(
                        next_node, 'grv-usedalready') != 'yes':
                outer = " " + self.parser.outerHtml(next_node) + " "
                replacement_text.append(outer)
                nodes_to_remove.append(next_node)
                self.parser.setAttribute(next_node, attr='grv-usedalready',
                                         value='yes')
                next_node = self.parser.nextSibling(next_node)

    def get_replacement_nodes(self, doc, div):
        replacement_text = []
        nodes_to_return = []
        nodes_to_remove = []
        kids = self.parser.childNodesWithText(div)
        for kid in kids:
            # The node is a <p> and already has some replacement text
            if self.parser.getTag(kid) == 'p' and len(replacement_text) > 0:
                new_node = self.get_flushed_buffer(
                    ''.join(replacement_text), doc)
                nodes_to_return.append(new_node)
                replacement_text = []
                nodes_to_return.append(kid)
            # The node is a text node
            elif self.parser.isTextNode(kid):
                kid_text = self.parser.getText(kid)
                self.replace_walk_left_right(kid, kid_text, replacement_text,
                                             nodes_to_remove)
            else:
                nodes_to_return.append(kid)

        # flush out anything still remaining
        if(len(replacement_text) > 0):
            new_node = self.get_flushed_buffer(''.join(replacement_text), doc)
            nodes_to_return.append(new_node)
            replacement_text = []

        for n in nodes_to_remove:
            self.parser.remove(n)

        return nodes_to_return

    def replace_with_para(self, doc, div):
        # Cleanup tags with useless text
        tags = ['select']
        for node in self.parser.getElementsByTags(div, tags):
            self.parser.remove(node)
        self.parser.replaceTag(div, 'p')

    def div_to_para(self, doc, dom_types):
        bad_divs = 0
        else_divs = 0
        tags = {'a', 'blockquote', 'dl', 'div', 'img', 'ol', 'p',
                'pre', 'table', 'ul'}
        nodes_with_tags = set()
        nodes = list(doc.iter())
        # Nodes are in depth first order, so iterate in reverse order
        # to visit children before parents
        for node in reversed(nodes):
            if node.tag in tags or node in nodes_with_tags:
                nodes_with_tags.add(node.getparent())
        for div in nodes:
            if div.tag not in dom_types:
                continue
            if (div is not None and div not in nodes_with_tags and self.parser.hasText(div)):
                self.replace_with_para(doc, div)
                bad_divs += 1
            elif div is not None:
                replace_nodes = self.get_replacement_nodes(doc, div)
                replace_nodes = [n for n in replace_nodes if n is not None]
                attrib = copy.deepcopy(div.attrib)
                div.clear()
                for i, node in enumerate(replace_nodes):
                    div.insert(i, node)
                for name, value in attrib.items():
                    div.set(name, value)
                else_divs += 1
        return doc

    def article_to_para(self, doc):
        article_nodes = []
        for node in doc.iter():
            for selector in ('id', 'class'):
                value = node.attrib.get(selector) or ''
                if self.article_nodes_re.search(value):
                    article_nodes.append(node)
        for node in article_nodes:
            self.replace_with_para(doc, node)
        return doc
