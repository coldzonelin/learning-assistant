import io
import tempfile
import unittest
from unittest.mock import patch
from datetime import date, timedelta

from app import create_app
from app.extensions import db
from app.models import Material


class EndpointsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':'sqlite://','UPLOAD_FOLDER':self.directory.name})
        self.ctx=self.app.app_context();self.ctx.push();db.create_all();self.client=self.app.test_client()

    def tearDown(self):
        db.session.remove();db.drop_all();self.ctx.pop();self.directory.cleanup()

    def upload(self, filename, content):
        return self.client.post('/api/v1/materials',data={'file':(io.BytesIO(content),filename)},content_type='multipart/form-data')

    @patch('app.api.ai.llm.weekly_report',return_value='# 学习报告\n- 学习注意力')
    @patch('app.api.ai.llm.generate_questions')
    @patch('app.api.ai.llm.chat')
    def test_full_workflow(self,chat,generate,report):
        uploaded=self.upload('学习.md','# 注意力\n注意力机制聚合上下文。'.encode()).get_json()['data']
        self.assertEqual(uploaded['status'],'ready'); mid=uploaded['id']
        self.assertEqual(self.client.get('/api/v1/materials').get_json()['data']['total'],1)
        self.assertEqual(self.client.get('/api/v1/materials/'+mid).get_json()['data']['file_size'],len('# 注意力\n注意力机制聚合上下文。'.encode()))
        conversation=self.client.post('/api/v1/conversations',json={'material_ids':[mid]}).get_json()['data']['id']
        def reply(question,chunks,history):
            self.assertIn('聚合上下文',chunks[0]['content'])
            return {'answer':'注意力聚合上下文。','source_chunk_ids':[chunks[0]['id']]}
        chat.side_effect=reply
        message=self.client.post(f'/api/v1/conversations/{conversation}/messages',json={'content':'注意力是什么？'}).get_json()['data']
        self.assertIn('聚合上下文',message['assistant_message']['sources'][0]['excerpt'])
        def make(chunks,counts,existing):
            return {'questions':[{'type':'single_choice','content':'注意力？','options':[{'key':x,'content':x} for x in 'ABCD'],'correct_answer':'A','grading_points':None,'knowledge_points':['注意力'],'source_chunk_ids':[chunks[0]['id']],'difficulty':'简单'}]}
        generate.side_effect=make
        assessment=self.client.post('/api/v1/assessments',json={'material_ids':[mid],'question_counts':{'single_choice':1,'true_false':0,'short_answer':0}}).get_json()['data']['id']
        question=self.client.get('/api/v1/assessments/'+assessment).get_json()['data']['questions'][0]
        response=self.client.post(f'/api/v1/assessments/{assessment}/submit',json={'answers':[{'question_id':question['id'],'answer':'B'}]})
        self.assertEqual(response.get_json()['data']['status'],'completed')
        self.assertEqual(self.client.post(f'/api/v1/assessments/{assessment}/submit',json={'answers':[]}).status_code,409)
        self.assertEqual(self.client.get('/api/v1/progress/weak-points').get_json()['data']['total'],1)
        summary=self.client.get('/api/v1/progress/summary').get_json()['data'];self.assertEqual(summary['average_score'],0);self.assertEqual(summary['weak_point_count'],1)
        today=date.today();monday=today-timedelta(days=today.weekday())
        weekly=self.client.post('/api/v1/weekly-reports',json={'week_start':monday.isoformat()}).get_json()['data']
        custom=self.client.post('/api/v1/weekly-reports',json={'start_date':monday.isoformat(),'end_date':today.isoformat()}).get_json()['data']
        self.assertNotEqual(weekly['id'],custom['id'])
        self.assertIn('学习报告',self.client.get('/api/v1/weekly-reports/'+custom['id']+'/download').get_data(as_text=True))
        self.assertEqual(self.client.delete('/api/v1/conversations/'+conversation).status_code,200)
        self.assertEqual(self.client.delete('/api/v1/materials/'+mid).status_code,200)

    def test_invalid_upload_and_retry(self):
        self.assertEqual(self.upload('bad.exe',b'abc').status_code,400)
        material=self.upload('bad.pdf',b'not a pdf').get_json()['data'];self.assertEqual(material['status'],'failed')
        retried=self.client.post('/api/v1/materials/'+material['id']+'/retry').get_json()['data'];self.assertEqual(retried['status'],'failed')
        self.assertTrue(retried['failure_reason'])

    def test_docx_and_pptx_extraction(self):
        from docx import Document
        from pptx import Presentation
        word=Document();word.add_paragraph('大模型课程内容'); word_bytes=io.BytesIO();word.save(word_bytes)
        uploaded=self.upload('course.docx',word_bytes.getvalue()).get_json()['data']
        self.assertEqual(uploaded['status'],'ready')
        slides=Presentation(); slide=slides.slides.add_slide(slides.slide_layouts[1]);slide.shapes.title.text='Transformer'
        ppt_bytes=io.BytesIO();slides.save(ppt_bytes)
        uploaded=self.upload('course.pptx',ppt_bytes.getvalue()).get_json()['data']
        self.assertEqual(uploaded['status'],'ready')

    @patch('app.api.ai.llm.generate_questions')
    def test_judgment_options_and_boolean_scoring(self, generate):
        material=self.upload('course.txt','注意力机制。'.encode()).get_json()['data']
        def make(chunks,counts,existing):
            return {'questions':[{'type':'true_false','content':'判断','options':None,'correct_answer':True,'grading_points':None,'knowledge_points':['注意力'],'source_chunk_ids':[chunks[0]['id']],'difficulty':'简单'}]}
        generate.side_effect=make
        created=self.client.post('/api/v1/assessments',json={'material_ids':[material['id']],'question_counts':{'single_choice':0,'true_false':1,'short_answer':0}}).get_json()['data']
        question=self.client.get('/api/v1/assessments/'+created['id']).get_json()['data']['questions'][0]
        self.assertEqual(question['options'],{'A':'正确','B':'错误'})
        self.client.post('/api/v1/assessments/'+created['id']+'/submit',json={'answers':[{'question_id':question['id'],'answer':True}]})
        result=self.client.get('/api/v1/assessments/'+created['id']+'/result').get_json()['data']
        self.assertEqual(result['total_score'],1)

    def test_user_isolation(self):
        other=Material(user_id='other',name='other.txt',file_type='txt',file_path='/tmp/x',status='ready')
        db.session.add(other);db.session.commit();identifier=other.id
        self.assertEqual(self.client.get('/api/v1/materials/'+identifier).status_code,404)
        self.assertEqual(self.client.delete('/api/v1/materials/'+identifier).status_code,404)


if __name__=='__main__': unittest.main()
