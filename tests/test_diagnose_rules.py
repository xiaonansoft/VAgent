
import unittest
from backend.app.schemas import SlagAnalysis, ProcessData, IronInitialAnalysis
from backend.app.tools.diagnose_process_quality import diagnose_process_quality

class TestDiagnoseRules(unittest.TestCase):

    def test_normal_case(self):
        slag = SlagAnalysis(V2O5=15.0, TFe=25.0, CaO=0.5)
        process = ProcessData(
            final_temp_c=1360.0, 
            lance_height_min=1500, 
            tap_time_min=5.0,
            is_one_can=True
        )
        iron = IronInitialAnalysis(C=3.5, Si=0.15, V=0.3, Ti=0.1, P=0.05, S=0.02)
        
        result = diagnose_process_quality(slag=slag, process=process, iron_analysis=iron)
        titles = [f.title for f in result.findings]
        self.assertIn("提钒过程质量受控", titles)
        self.assertEqual(len(result.findings), 1)

    def test_severe_carbon_oxidation(self):
        slag = SlagAnalysis(TFe=10.0, V2O5=14.0)
        process = ProcessData(final_temp_c=1410.0) # > 1400
        
        result = diagnose_process_quality(slag=slag, process=process)
        titles = [f.title for f in result.findings]
        self.assertIn("严重碳氧化导致钒收得率下降", titles)
        finding = next(f for f in result.findings if f.title == "严重碳氧化导致钒收得率下降")
        self.assertIn("Tc ~ 1360-1380℃", finding.root_cause)
        self.assertIn("缩短吹炼时间", finding.recommendation[2])

    def test_splashing_risk(self):
        slag = SlagAnalysis()
        process = ProcessData(
            final_temp_c=1360.0, # > 1350
            lance_height_min=1000 # < 1100
        )
        
        result = diagnose_process_quality(slag=slag, process=process)
        titles = [f.title for f in result.findings]
        self.assertIn("喷溅风险极高", titles)
        finding = next(f for f in result.findings if f.title == "喷溅风险极高")
        self.assertIn("C + O -> CO", finding.root_cause)
        self.assertIn("提升枪位至 1.4m 以上", finding.recommendation[0])

    def test_dry_slag(self):
        slag = SlagAnalysis(TFe=8.0) # < 10
        process = ProcessData(final_temp_c=1390.0) # > 1380
        
        result = diagnose_process_quality(slag=slag, process=process)
        titles = [f.title for f in result.findings]
        self.assertIn("炉渣返干 (Slag Reversion)", titles)
        finding = next(f for f in result.findings if f.title == "炉渣返干 (Slag Reversion)")
        self.assertIn("FeO + C -> Fe + CO", finding.root_cause)

    def test_low_v2o5(self):
        slag = SlagAnalysis(V2O5=10.0) # < 12.5
        process = ProcessData()
        
        result = diagnose_process_quality(slag=slag, process=process)
        titles = [f.title for f in result.findings]
        self.assertIn("钒渣品位偏低 (V2O5 < 12.5%)", titles)

    def test_si_dilution(self):
        slag = SlagAnalysis()
        process = ProcessData()
        iron = IronInitialAnalysis(C=3.5, Si=0.30, V=0.3, Ti=0.1, P=0.05, S=0.02) # Si > 0.25
        
        result = diagnose_process_quality(slag=slag, process=process, iron_analysis=iron)
        titles = [f.title for f in result.findings]
        self.assertIn("高硅稀释效应 (Si Dilution)", titles)

    def test_raw_material_deficit(self):
        slag = SlagAnalysis()
        process = ProcessData()
        # V / (Si + Ti) = 0.2 / (0.15 + 0.1) = 0.2 / 0.25 = 0.8 < 1.01
        iron = IronInitialAnalysis(C=3.5, Si=0.15, V=0.2, Ti=0.1, P=0.05, S=0.02)
        
        result = diagnose_process_quality(slag=slag, process=process, iron_analysis=iron)
        titles = [f.title for f in result.findings]
        self.assertIn("原料结构比值失衡 (Raw Material Deficit)", titles)

    def test_slag_contamination(self):
        slag = SlagAnalysis(CaO=3.0) # > 2.0
        process = ProcessData(is_one_can=True)
        
        result = diagnose_process_quality(slag=slag, process=process)
        titles = [f.title for f in result.findings]
        self.assertIn("高炉渣混入污染 (Slag Contamination)", titles)

    def test_tap_time_short(self):
        slag = SlagAnalysis()
        process = ProcessData(tap_time_min=3.0) # < 3.5
        
        result = diagnose_process_quality(slag=slag, process=process)
        titles = [f.title for f in result.findings]
        self.assertIn("出钢时间过短，富钒渣流失风险", titles)

if __name__ == '__main__':
    unittest.main()
