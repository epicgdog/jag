import unittest
from types import SimpleNamespace
from journal.notion import snapshot
from journal.obsidian import JournalError
class NotionTests(unittest.TestCase):
    def test_nested_pagination_and_tasks(self):
        page={'last_edited_time':'2025-01-01T00:00:00Z','properties':{'Name':{'type':'title','title':[{'plain_text':'12/31/2025'}]}}}
        def block(id,kind,text,children=False,checked=False):
            return {'id':id,'type':kind,'has_children':children,kind:{'rich_text':[{'plain_text':text}],'checked':checked}}
        def listing(block_id,page_size,start_cursor=None):
            if block_id=='12345678-1234-1234-1234-123456789abc':
                if start_cursor: return {'results':[block('b','to_do','two',checked=True)],'has_more':False}
                return {'results':[block('a','paragraph','text',True)],'has_more':True,'next_cursor':'next'}
            return {'results':[block('c','to_do','one')],'has_more':False}
        client=SimpleNamespace(pages=SimpleNamespace(retrieve=lambda **kw:page),blocks=SimpleNamespace(children=SimpleNamespace(list=listing)))
        doc=snapshot(client,'12345678123412341234123456789abc')
        self.assertEqual(doc['document_date'],'2025-12-31')
        self.assertEqual([(t['id'],t['checked']) for t in doc['tasks']],[('c',False),('b',True)])
        self.assertIn('one',doc['content'])
    def test_inconsistent_snapshot(self):
        counter=iter([1,2,3,4])
        client=SimpleNamespace(pages=SimpleNamespace(retrieve=lambda **kw:{'last_edited_time':next(counter)}),blocks=SimpleNamespace(children=SimpleNamespace(list=lambda **kw:{'results':[]})))
        with self.assertRaises(JournalError): snapshot(client,'12345678123412341234123456789abc')
    def test_columns_toggle_media_and_override(self):
        page={'last_edited_time':'same','properties':{'Name':{'type':'title','title':[{'plain_text':'Synthetic'}]}}}
        def b(id,kind,children=False):
            return {'id':id,'type':kind,'has_children':children,kind:{'rich_text':[{'plain_text':'synthetic'}],'checked':False}}
        tree={'12345678-1234-1234-1234-123456789abc':[b('cols','column_list',True),b('image','image')], 'cols':[b('col','column',True)], 'col':[b('toggle','toggle',True)], 'toggle':[b('task','to_do')]}
        client=SimpleNamespace(pages=SimpleNamespace(retrieve=lambda **kw:page),blocks=SimpleNamespace(children=SimpleNamespace(list=lambda block_id,**kw:{'results':tree[block_id]})))
        doc=snapshot(client,'12345678123412341234123456789abc','Missing','2025-01-01')
        self.assertEqual(doc['document_date'],'2025-01-01')
        self.assertEqual(doc['tasks'][0]['id'],'task')
        self.assertEqual(doc['content'].count('synthetic'),2)
    def test_synthetic_snapshot_to_storage(self):
        from test_pipeline import Model, Store
        page={'last_edited_time':'same','properties':{'Name':{'type':'title','title':[{'plain_text':'2025-01-01'}]}}}
        todo={'id':'task','type':'to_do','has_children':False,'to_do':{'rich_text':[{'plain_text':'synthetic'}],'checked':True}}
        client=SimpleNamespace(pages=SimpleNamespace(retrieve=lambda **kw:page),blocks=SimpleNamespace(children=SimpleNamespace(list=lambda **kw:{'results':[todo]})))
        doc=snapshot(client,'12345678123412341234123456789abc')
        store=Store(); store.save(doc,Model().summarize(doc['document_date'],doc['content']))
        self.assertEqual(len(store.docs),1)
        self.assertTrue(store.docs[doc['id']][0]['tasks'][0]['checked'])
