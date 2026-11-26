# SPDX-License-Identifier: AGPL-3.0-or-later
"""Calendar, interface, and explicit-clause checks; not empirical validation."""
from pathlib import Path
import json,os,subprocess,sys,unittest
from datetime import datetime,timedelta,timezone
from lunar_python import Solar
from open_birth_chart import bazi_engine as bz
from open_birth_chart.ziwei_engine import ZiweiEngine


def row(date='2000-08-16T12:00:00',sex='F',offset=28800):
    return {'study_id':'synthetic_test','birth_local':date,'sex':sex,'source_offset_seconds':offset,'calendar':'gregorian'}


class BaziTests(unittest.TestCase):
    def test_upstream_published_golden_pillars(self):
        # Author-maintained test/EightCharTest.py, SHA recorded in provenance.
        cases=[('2005-12-23T08:37:00',['乙酉','戊子','辛巳','壬辰']),
               ('1999-07-21T16:00:00',['己卯','辛未','甲戌','壬申']),
               ('1939-08-05T16:00:00',['己卯','辛未','甲戌','壬申']),
               ('1901-01-01T12:00:00',['庚子','戊子','己卯','庚午']),
               ('1960-12-17T12:00:00',['庚子','戊子','己卯','庚午']),
               ('1987-08-03T02:00:00',['丁卯','丁未','甲申','乙丑']),
               ('1900-01-29T16:00:00',['己亥','丁丑','壬寅','戊申']),
               ('1959-12-17T16:00:00',['己亥','丙子','癸酉','庚申'])]
        for date,expected in cases:
            with self.subTest(date=date):
                self.assertEqual(expected,[p['ganzhi'] for p in bz.build_natal(row(date))['pillars'].values()])

    def test_independent_day_cycle_and_23_boundary(self):
        anchor=datetime(1901,1,1);index=bz.JIAZI.index('己卯')
        for y in range(1880,2020,7):
            for hour in [0,22,23]:
                dt=datetime(y,7,7,hour,30)
                day=dt+timedelta(days=int(hour==23))
                expected=bz.JIAZI[(index+(day.date()-anchor.date()).days)%60]
                self.assertEqual(expected,bz.build_natal(row(dt.isoformat()))['pillars']['day']['ganzhi'])

    def test_same_instant_season_and_qiyun_across_zones(self):
        term=Solar.fromYmd(2000,7,1).getLunar().getJieQiTable()['立春']
        absolute=bz._datetime_solar(term).replace(tzinfo=bz.CST).astimezone(bz.UTC)
        before=[];after=[]
        for delta,output in [(-1,before),(1,after)]:
            for offset in [-28800,0,28800,50400]:
                t=absolute+timedelta(seconds=delta)
                civil=t.replace(tzinfo=None)+timedelta(seconds=offset)
                r=row(civil.isoformat(),'M',offset);r['birth_utc']=t.isoformat()
                c=bz.build_natal(r)
                output.append((c['pillars']['year']['ganzhi'],c['pillars']['month']['ganzhi'],c['qiyun']['start_utc']))
        self.assertEqual(len(set(before)),1);self.assertEqual(len(set(after)),1)
        self.assertNotEqual(before[0][:2],after[0][:2])

    def test_qiyun_minute_conversion_and_no_decadal_gaps(self):
        for sex in ['F','M']:
            c=bz.build_natal(row(sex=sex));ec=Solar.fromYmdHms(2000,8,16,12,0,0).getLunar().getEightChar()
            forward=c['qiyun']['direction']=='forward';term=ec.getLunar().getNextJie() if forward else ec.getLunar().getPrevJie()
            termdt=bz._datetime_solar(term.getSolar()).replace(second=0)
            diff=abs(int((termdt-datetime(2000,8,16,12)).total_seconds()/60))
            q=c['qiyun'];reconstructed=q['delay_years']*4320+q['delay_months']*360+q['delay_days']*12+q['delay_hours']/2
            self.assertEqual(diff,reconstructed)
            self.assertTrue(all(a['end_utc_exclusive']==b['start_utc'] for a,b in zip(c['decades'],c['decades'][1:])))
            self.assertTrue(all(bz.annual_signals(c,y)['primary_score'] is not None for y in range(2021,2061)))

    def test_invalid_data_abstain_not_zero(self):
        for changes in [{'sex':None},{'birth_local':'2000-08-16'}, {'birth_utc':'2000-08-16T00:00:00Z'}, {'source_offset_seconds':None}]:
            r=row();r.update(changes)
            self.assertEqual('abstain',bz.evaluate(r,[2030])['status'])
            self.assertIsNone(bz.evaluate(r,[2030])['annual'][0]['score'])

    def test_declared_relations_and_ten_gods(self):
        self.assertTrue(bz.relation('甲子','庚午')['stem_control_branch_clash'])
        self.assertTrue(bz.relation('甲子','己丑')['stem_and_branch_combination'])
        self.assertFalse(bz.relation('甲子','甲子')['branch_clash'])
        self.assertEqual('七杀',bz.describe_pillar('庚午','甲')['stem_ten_god'])
        self.assertEqual('劫财',bz.describe_pillar('乙卯','甲')['stem_ten_god'])

    def test_source_clause_support_damage_and_rescue_coexist(self):
        x=bz.interpret_pillars({'year':'壬子','month':'辛酉','day':'甲寅','hour':'丁卯'})
        matches={c['rule'] for c in x['clause_matches'] if c['structural_match']}
        self.assertTrue({'BZC02a','BZC02b'}<=matches)
        self.assertIsNone(x['net_fortune_verdict'])
        self.assertIsNone(x['strength_evidence']['classical_strong_weak_verdict'])

    def test_killings_control_resource_counterexample(self):
        x=bz.interpret_pillars({'year':'丁卯','month':'辛酉','day':'乙卯','hour':'癸未'},{'yearly':'己丑'})
        matches={c['rule'] for c in x['clause_matches'] if c['structural_match']}
        self.assertTrue({'BZC05a','BZC05b','BZC05c'}<=matches)
        self.assertIsNone(x['net_fortune_verdict'])

    def test_original_mixed_killings_fixture_must_abstain(self):
        # The original test incorrectly expected a unique seven-killings pattern
        # even though both 庚 and 壬 are exposed from 申. Retain the counterexample.
        x=bz.interpret_pillars({'year':'丙寅','month':'庚申','day':'甲午','hour':'壬申'},{'yearly':'戊辰'})
        self.assertEqual('competing_exposed_candidates',x['month_command']['selection_status'])
        self.assertIsNone(x['month_command']['selected_candidate'])
        self.assertFalse(x['month_command']['unique_yongshen_adjudicated'])
        self.assertFalse(any(c['structural_match'] for c in x['clause_matches'] if c['rule'].startswith('BZC05')))

    def test_competing_use_god_candidates_remain_unresolved(self):
        x=bz.interpret_pillars({'year':'丙申','month':'甲寅','day':'庚午','hour':'戊寅'})
        self.assertEqual('competing_exposed_candidates',x['month_command']['selection_status'])
        self.assertFalse(x['month_command']['unique_yongshen_adjudicated'])

    def test_transformation_counterexample_not_plain_officer(self):
        x=bz.interpret_pillars({'year':'甲卯','month':'辛亥','day':'丁未','hour':'庚子'})
        self.assertEqual('transformation_premises_require_adjudication',x['month_command']['selection_status'])
        self.assertFalse(x['month_command']['unique_yongshen_adjudicated'])


class ZiweiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.z=ZiweiEngine()
    @classmethod
    def tearDownClass(cls):cls.z.close()

    def test_independent_life_body_palace_formula(self):
        for sex in ['M','F']:
            for hour in [0,1,3,5,7,9,11,13,15,17,19,21,23]:
                r=row(f'2000-08-16T{hour:02}:00:00',sex)
                a=self.z.compute(r,[2026],include_chart=True,detailed=True)
                self.assertEqual('computed_for_registered_conventions',a['status'])
                lunar=a['chart']['raw_lunar_date'];month=lunar['lunarMonth']
                hourbranch=((hour+1)//2)%12
                expected_life=(month-1-hourbranch)%12;expected_body=(month-1+hourbranch)%12
                palaces=a['chart']['palaces']
                self.assertEqual(expected_life,next(p['index'] for p in palaces if p['name']=='命宫'))
                self.assertEqual(expected_body,next(p['index'] for p in palaces if p['is_body_palace']))
                self.assertEqual(14,sum(len(p['major_stars']) for p in palaces))

    def test_golden_2026_transformations_and_year_palace(self):
        a=self.z.compute(row(),[2026],include_chart=True,detailed=True)
        y=a['annual'][0]['yearly']
        self.assertEqual(['天同','天机','文昌','廉贞'],[x['star'] for x in y['transformations']])
        self.assertEqual('午',y['earthly_branch']);self.assertEqual(4,y['index'])
        self.assertEqual(['紫微','天府'],[s['name'] for s in a['chart']['palaces'][0]['major_stars']])

    def test_23_forward_same_effective_chart(self):
        a=self.z.compute(row('2000-08-16T23:30:00'),[2026],include_chart=True)
        b=self.z.compute(row('2000-08-17T00:30:00'),[2026],include_chart=True)
        self.assertEqual(a['chart']['palaces'],b['chart']['palaces'])
        self.assertEqual(a['annual'],b['annual'])

    def test_40_years_cycle_coverage_and_compact_scores(self):
        a=self.z.compute(row(),list(range(2021,2061)),detailed=True)
        self.assertEqual(40,len(a['annual']))
        for y in a['annual']:
            self.assertEqual('computed_for_registered_conventions',y['status'])
            self.assertEqual((int(y['yearly']['ji_in_focus'])+int(y['decadal']['ji_in_focus']))/2,y['score'])
            self.assertTrue(0<=y['score']<=1)

    def test_unknown_inputs_abstain(self):
        for r in [row(sex=None),row(date='2000-08-16'),row(date='2000-02-30T12:00:00')]:
            a=self.z.compute(r,[2026]);self.assertEqual('abstain',a['status']);self.assertIsNone(a['annual'][0]['score'])

    def test_runtime_timezone_does_not_change_civil_chart(self):
        bridge=Path(__file__).parents[1]/'src/open_birth_chart/ziwei_bridge.cjs'
        request=json.dumps({'row':row(),'years':[2026,2040,2060],'include_chart':True})+'\n'
        results=[]
        for zone in ['UTC','America/Los_Angeles','Pacific/Kiritimati']:
            p=subprocess.run(['node',str(bridge)],input=request,text=True,capture_output=True,check=True,env={**os.environ,'TZ':zone})
            results.append(json.loads(p.stdout))
        self.assertEqual(results[0],results[1]);self.assertEqual(results[0],results[2])

    def test_qisha_rescue_and_adverse_context_are_both_retained(self):
        bridge=Path(__file__).parents[1]/'src/open_birth_chart/ziwei_bridge.cjs'
        script=r'''
const {clauses}=require(process.argv[1]);
const p=Array.from({length:12},(_,index)=>({index,name:index===0?'命宫':'other',majorStars:[],minorStars:[],adjectiveStars:[]}));
p[0].majorStars=[{name:'七杀',brightness:'庙'}];
p[4].majorStars=[{name:'紫微',brightness:'旺'}];
p[0].minorStars=[{name:'擎羊',type:'tough'}];
const empty=()=>Array.from({length:12},()=>[]);
const ys=empty();ys[0]=[{name:'流羊',type:'tough'}];
const scope={index:0,transformations:[{palaces:[0]},{palaces:[4]},{palaces:[8]},{palaces:[0]}],ji_in_focus:true,native_six_malefics_in_focus:['擎羊'],positive_transformations_in_focus:1,native_benefics_in_focus:[]};
const h={decadal:{stars:empty()},yearly:{stars:ys},age:{index:0}};
const c=clauses({palaces:p},h,new Map([['七杀',[0]],['紫微',[4]]]),scope,scope);
process.stdout.write(JSON.stringify(c));
'''
        p=subprocess.run(['node','-e',script,str(bridge.resolve())],text=True,capture_output=True,check=True)
        x=json.loads(p.stdout);rules={r['rule']:r for r in x['clauses']}
        self.assertTrue(rules['ZWC03']['structural_match'])
        self.assertTrue(rules['ZWC03']['temple_mitigation'])
        self.assertEqual([{'palace':4,'star':'紫微'}],rules['ZWC03']['rescue_context'])
        self.assertTrue(rules['ZWC04']['structural_match'])
        self.assertTrue(rules['ZWC05']['structural_match'])
        self.assertIsNone(x['net_fortune_verdict'])


if __name__=='__main__':unittest.main(verbosity=2)
