import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import sys
from cli_anything.ableton.preparation import prepare
from cli_anything.ableton.production.workspace import Workspace
from cli_anything.ableton.production.ledger import Ledger

class Learning(unittest.TestCase):
    def test_learning_route_loads_map_without_execution_claim(self):
        result=prepare({'task':'learn','request':'Map tested outcomes and feedback'})
        self.assertEqual([r['tool'] for r in result['context_requests']],['ableton_methods','ableton_recall'])
        recall=result['context_requests'][1]
        self.assertEqual(recall['arguments'],{'query':'learning-map','limit':3})
        self.assertIsNone(result['next_action']['tool'])
        self.assertFalse(result['needs_live'])
        self.assertFalse(result['capabilities']['perceptual_listener'])
        self.assertFalse(result['capabilities']['playback_opt_in'])
        specific=prepare({'task':'learn','request':'Map evidence','style':'acid','plugin_query':'Pigments'})
        self.assertEqual(specific['context_requests'][1]['arguments'],{'query':'learning-map','limit':3})
        self.assertEqual(specific['context_requests'][2]['tool'],'ableton_plugin_context')
        self.assertEqual(specific['context_requests'][2]['arguments']['query'],'Pigments')

    def test_learning_route_requires_workspace_and_is_pure(self):
        from unittest.mock import patch
        with patch('builtins.open',side_effect=AssertionError('No file I/O')),patch('socket.socket',side_effect=AssertionError('No sockets')):
            result=prepare({'task':'learn','request':'Map evidence'},workspace_enabled=False)
        self.assertTrue(result['blockers'])
        self.assertEqual(result['context_requests'],[])
        self.assertIsNone(result['next_action']['tool'])

    def test_sdk_retrieves_map_as_measured_evidence(self):
        asyncio.run(self._sdk())

    async def _sdk(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger=Ledger(Workspace(tmp))
            event=ledger.append('review',['learning-map'],{'evidence_type':'measured_learning_map','lesson':'Known signal checks do not approve musical quality','model_training':False,'creative_acceptance':'pending'})
            from cli_anything.ableton.mcp_server import create_server
            class NoLive:
                def call(self,*args,**kwargs):
                    raise AssertionError('Learning context reached Live')
            server=create_server(client=NoLive(),workspace=tmp)
            await server.call_tool('ableton_prepare',{'task':'learn','request':'Map evidence'})
            await server.call_tool('ableton_recall',{'query':'learning-map','limit':3})
            self.assertEqual(len(await server.list_tools()),23)
            params=StdioServerParameters(command=str(Path(sys.executable).parent/'ableton-mcp'),args=['--workspace',tmp])
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize()
                    names=[t.name for t in (await session.list_tools()).tools]
                    self.assertEqual(len(names),23)
                    self.assertNotIn('ableton_apply',names)
                    p=await session.call_tool('ableton_prepare',{'task':'learn','request':'Refresh map'})
                    self.assertFalse(p.isError)
                    self.assertIn('ableton_recall',json.dumps(json.loads(p.content[0].text)['context_requests']))
                    r=await session.call_tool('ableton_recall',{'query':'learning-map','limit':3})
                    self.assertFalse(r.isError)
                    events=json.loads(r.content[0].text)['events']
                    self.assertEqual(len(events),1)
                    self.assertEqual(events[0]['id'],event)
                    self.assertEqual(events[0]['kind'],'review')
                    self.assertNotEqual(events[0]['payload'].get('evidence_type'),'explicit_user_feedback')
                    self.assertFalse(events[0]['payload']['model_training'])
if __name__=='__main__':unittest.main(verbosity=2)
