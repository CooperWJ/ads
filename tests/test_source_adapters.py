"""上游导出与 PDF 解析边界：保留页/节点定位和未知区域。"""
import io
import json
import unittest

from ads.source_adapters import pdf_units, json_units
from ads.project import Blocked


class ExportAdapterTests(unittest.TestCase):
    def test_docling_text_table_and_unread_visual_are_separate(self):
        exported = {'schema_name':'DoclingDocument','pages':{'1':{}},
                    'texts':[{'text':'Synthetic requirement','prov':[{'page_no':1}]}],
                    'tables':[{'data':{'grid':[[{'text':'field'}, {'text':'value'}]]}}],
                    'pictures':[{'id':'synthetic-picture'}]}
        units, meta = json_units('source.json', json.dumps(exported).encode())
        self.assertEqual(len(units), 3)
        self.assertEqual(units[0]['provenance'][0]['page_no'], 1)
        self.assertIn('PICTURES_REQUIRE_VISUAL_REVIEW', meta['unknown'])

    def test_figma_inventory_includes_hidden_text_and_frame_nodes(self):
        exported = {'document':{'id':'0:0','type':'DOCUMENT','children':[
            {'id':'1:0','type':'FRAME','children':[{'id':'2:0','type':'TEXT','characters':'Save','visible':False}]}]}}
        units, meta = json_units('figma.json', json.dumps(exported).encode())
        self.assertEqual(len(meta['nodes']), 3)
        self.assertEqual(units[0]['node_id'], '2:0')
        self.assertFalse(units[0]['visible'])

    def test_unknown_json_cannot_be_empty_success(self):
        with self.assertRaises(ValueError):
            json_units('unknown.json', b'{"unrecognized":true}')

    def test_real_pdf_text_and_blank_page_do_not_share_same_verdict(self):
        try:
            from reportlab.pdfgen.canvas import Canvas
            from pypdf import PdfWriter
        except ImportError:
            self.skipTest('optional PDF dependencies required')
        target = io.BytesIO()
        canvas = Canvas(target)
        canvas.drawString(72, 720, 'Synthetic source requirement')
        canvas.save()
        units, meta = pdf_units('synthetic.pdf', target.getvalue())
        self.assertIn('Synthetic source requirement', units[0]['text'])
        self.assertEqual(meta['pages'], 1)
        blank = io.BytesIO()
        writer = PdfWriter();writer.add_blank_page(width=200, height=200);writer.write(blank)
        units, meta = pdf_units('blank.pdf', blank.getvalue())
        self.assertFalse(units)
        self.assertIn('page:1:NO_TEXT_LAYER', meta['unknown'])


if __name__ == '__main__':
    unittest.main()
