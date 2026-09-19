-- =================================================================
-- BRAHMO Clinical AI — Seed Data
-- Generated from brahmo_research_data.xlsx (verified on 1mg.com)
-- =================================================================

-- Clear existing data (idempotent)
TRUNCATE TABLE drug_interactions, hospital_formulary, indian_guidelines, drugs, patients RESTART IDENTITY CASCADE;

-- =================================================================
-- DRUGS (48 rows)
-- =================================================================
INSERT INTO drugs (id, generic_name, generic_name_normalized, drug_class, drug_subclass,
                   indian_brand_name, manufacturer, mrp_price, nlem_status, renal_dosing,
                   hf_safe, weight_effect, hypoglycemia_risk, condition_tags, source_url, notes) VALUES
  (1, 'Metformin', 'metformin', 'Biguanide', NULL, 'Glyciphage SR', 'Franco-Indian Pharmaceuticals Private Ltd', '26.62/strip of 10 (500mg)', TRUE, '{"egfr_45_plus": "full dose", "egfr_30_45": "reduce 50%", "egfr_below_30": "STOP"}'::jsonb, TRUE, 'neutral', 'low', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/glyciphage-sr-500mg-tablet-149311', 'First-line. NLEM. Hold 48h pre/post contrast. B12 deficiency on prolonged use.'),
  (2, 'Glimepiride', 'glimepiride', 'Sulfonylurea', '2nd-gen SU', 'Amaryl', 'Sanofi India Ltd', '₹115/strip of 10 (1mg)', TRUE, '{"egfr_60_plus": "full dose", "egfr_30_60": "reduce, caution", "egfr_below_30": "STOP - hypoglycemia"}'::jsonb, TRUE, 'gain', 'high', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/amaryl-1mg-tablet-12155', 'Hypoglycemia risk HIGH in elderly, CKD, beta-blockers (masks symptoms).'),
  (3, 'Gliclazide', 'gliclazide', 'Sulfonylurea', '2nd-gen SU', 'Glizid MR', 'Mankind Pharma Ltd', '₹71.2/strip of 10 (30mg)', TRUE, '{"egfr_30_plus": "use cautiously", "egfr_below_30": "avoid"}'::jsonb, FALSE, 'gain', 'moderate', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/glizid-mr-30-tablet-11796', 'Preferred SU in India - lower hypoglycemia vs glimepiride.'),
  (4, 'Glibenclamide', 'glibenclamide', 'Sulfonylurea', '1st-gen SU', 'Daonil', 'Sanofi India Ltd', '₹58.9/strip of 30 (5mg)', TRUE, '{"egfr_60_plus": "use cautiously", "egfr_below_60": "STOP"}'::jsonb, FALSE, 'gain', 'high', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/daonil-tablet-333076', 'Older SU. Avoid in elderly and CKD. Highest hypoglycemia risk.'),
  (5, 'Teneligliptin', 'teneligliptin', 'DPP4 inhibitor', NULL, 'Dynaglipt Tablet', 'Mankind Pharma Ltd', '₹84.8/strip of 10 (20mg)', FALSE, '{"egfr_all": "no dose adjustment"}'::jsonb, TRUE, 'neutral', 'low', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/dynaglipt-tablet-323687', 'INDIA''s #1 DPP4i. Very rare in US/UK. Affordable (~₹6-8/tablet). Renal-safe.'),
  (6, 'Sitagliptin', 'sitagliptin', 'DPP4 inhibitor', NULL, 'Sitasys', 'Systopic Laboratories Pvt Ltd', '₹74.6/strip of 10 (100mg)', FALSE, '{"egfr_45_plus": "100mg", "egfr_30_45": "50mg", "egfr_below_30": "25mg"}'::jsonb, TRUE, 'neutral', 'low', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/sitasys-100mg-tablet-857560', 'Renal dose adjustment needed. Generally well tolerated.'),
  (7, 'Vildagliptin', 'vildagliptin', 'DPP4 inhibitor', NULL, 'Glyday', 'Elsker lifescience Pvt. Ltd.', '₹103/strip of 10 (50mg)', FALSE, '{"egfr_50_plus": "50mg BD", "egfr_below_50": "50mg OD"}'::jsonb, TRUE, 'neutral', 'low', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/glyday-50-tablet-575621', 'Monitor LFTs. Avoid in liver disease.'),
  (8, 'Linagliptin', 'linagliptin', 'DPP4 inhibitor', NULL, 'L Glip', 'Unison Pharmaceuticals Pvt Ltd', '₹25.3/strip of 10 (5mg)', FALSE, '{"egfr_all": "no dose adjustment - hepatic clearance"}'::jsonb, TRUE, 'neutral', 'low', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/l-glip-5mg-tablet-1003435', 'BEST choice in advanced CKD - no renal dose adjustment needed.'),
  (9, 'Saxagliptin', 'saxagliptin', 'DPP4 inhibitor', NULL, 'Zaxaglit', 'Chemo Healthcare Pvt Ltd', '₹365/strip of 10 (2.5mg)', FALSE, '{"egfr_45_plus": "5mg", "egfr_below_45": "2.5mg"}'::jsonb, FALSE, 'neutral', 'low', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/zaxaglit-2.5mg-tablet-668606', 'CONTRAINDICATED in HF (FDA black box - SAVOR-TIMI). Increased HF hospitalization.'),
  (10, 'Empagliflozin', 'empagliflozin', 'SGLT2 inhibitor', NULL, 'Gibtulio', 'Lupin Ltd', '₹117/strip of 10 (10mg)', FALSE, '{"egfr_45_plus": "10-25mg", "egfr_30_45": "10mg if started, do not initiate", "egfr_below_30": "STOP"}'::jsonb, TRUE, 'loss', 'low', '["diabetes", "cardiovascular", "heart_failure"]'::jsonb, 'https://www.1mg.com/drugs/gibtulio-10mg-tablet-336789', 'EMPEROR-Reduced: HF benefit. EMPA-REG OUTCOME: CV benefit. Genital infections, DKA risk.'),
  (11, 'Dapagliflozin', 'dapagliflozin', 'SGLT2 inhibitor', NULL, 'Oxra', 'Sun Pharmaceutical Industries Ltd', '₹162/strip of 14 (5mg)', FALSE, '{"egfr_25_plus": "10mg", "egfr_below_25": "STOP for glycemic; continue for HF if stable"}'::jsonb, TRUE, 'loss', 'low', '["diabetes", "cardiovascular", "heart_failure"]'::jsonb, 'https://www.1mg.com/drugs/oxra-5mg-tablet-333999', 'DAPA-HF trial: HFrEF benefit even without diabetes. First-line in HF + T2DM.'),
  (12, 'Canagliflozin', 'canagliflozin', 'SGLT2 inhibitor', NULL, 'Canagliflowin', 'Prevego Healthcare & Research Private Limited', '₹306.63/strip of 10 (100mg)', FALSE, '{"egfr_60_plus": "100-300mg", "egfr_30_60": "100mg", "egfr_below_30": "STOP"}'::jsonb, TRUE, 'loss', 'low', '["diabetes", "cardiovascular"]'::jsonb, 'https://www.netmeds.com/product/canagliflowin-100-tablet-10s-mb6p76-10893979', 'CANVAS: increased lower extremity amputation risk. Less commonly used in India now.'),
  (13, 'Pioglitazone', 'pioglitazone', 'Thiazolidinedione', NULL, 'piONORM', 'Micro Labs Ltd', '₹54.3/strip of 10 (15mg)', FALSE, '{"egfr_all": "no dose adjustment"}'::jsonb, FALSE, 'gain', 'low', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/pionorm-15-tablet-27703', 'CONTRAINDICATED in HF (fluid retention). Beneficial in NAFLD. Bladder cancer risk caution.'),
  (14, 'Insulin Glargine', 'insulin_glargine', 'Insulin', 'Long-acting analog', 'Basalog', 'Biocon', '₹542/cartridge (3ml)', FALSE, '{"egfr_all": "dose-adjust per glucose"}'::jsonb, TRUE, 'gain', 'high', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/basalog-refill-solution-for-injection-164232', 'Once-daily basal. Basalog (Biocon biosimilar) much cheaper than Lantus.'),
  (15, 'Insulin Human 30/70 (Premixed)', 'insulin_human_premix', 'Insulin', 'Premixed human', 'Huminsulin 30/70', 'Eli Lilly and Company India Pvt Ltd', '₹567/vial (10ml)', TRUE, '{"egfr_all": "dose-adjust per glucose"}'::jsonb, TRUE, 'gain', 'high', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/huminsulin-30-70-suspension-for-injection-100iu-ml-115297', 'NLEM. Cheapest insulin option. Twice-daily injection. Cloudy insulin.'),
  (16, 'Insulin Regular (Human)', 'insulin_regular', 'Insulin', 'Short-acting human', 'Huminsulin R', 'Eli Lilly and Company India Pvt Ltd', '₹154/vial (10ml)', TRUE, '{"egfr_all": "dose-adjust per glucose"}'::jsonb, TRUE, 'gain', 'high', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/huminsulin-r-40iu-ml-solution-for-injection-14549', 'NLEM. Used in DKA management IV. Cheap.'),
  (17, 'Liraglutide', 'liraglutide', 'GLP-1 RA', 'Daily injectable', 'Gliptoza', 'Eris Lifesciences Limited', '₹1691/pen (3ml)', FALSE, '{"egfr_15_plus": "use cautiously", "egfr_below_15": "avoid"}'::jsonb, TRUE, 'loss', 'low', '["diabetes", "cardiovascular"]'::jsonb, 'https://www.1mg.com/drugs/gliptoza-pre-filled-pen-1084868', 'LEADER trial: CV benefit. Weight loss. Expensive in India (~₹6000-9000/month).'),
  (18, 'Dulaglutide', 'dulaglutide', 'GLP-1 RA', 'Weekly injectable', 'Trulicity', 'Eli Lilly and Company India Pvt Ltd', '₹4999/pen (0.75mg/0.5ml)', FALSE, '{"egfr_15_plus": "no dose adjustment", "egfr_below_15": "avoid"}'::jsonb, TRUE, 'loss', 'low', '["diabetes", "cardiovascular"]'::jsonb, 'https://www.1mg.com/drugs/trulicity-0.75mg-pre-filled-pen-332260', 'REWIND: CV benefit. Once-weekly. Very expensive in India.'),
  (19, 'Acarbose', 'acarbose', 'Alpha-glucosidase inhibitor', NULL, 'Glucobay', 'Bayer Zydus Pharma Pvt Ltd', '₹102/strip of 10 (25mg)', FALSE, '{"egfr_25_plus": "use", "egfr_below_25": "avoid"}'::jsonb, TRUE, 'neutral', 'low', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/glucobay-25-tablet-40362', 'Targets postprandial glucose. GI side effects common.'),
  (20, 'Metformin + Glimepiride FDC', 'metformin_glimepiride', 'FDC', 'Biguanide+SU', 'Azulix', 'Torrent Pharmaceuticals Ltd', '₹63.9/strip of 10 (0.5mg+500mg', FALSE, '{"egfr_60_plus": "use", "egfr_below_60": "STOP - SU component unsafe"}'::jsonb, TRUE, 'gain', 'high', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/azulix-0.5-mf-tablet-pr-497053', 'Most common FDC in India. Glycomet-GP1 = 500mg+1mg, GP2 = 500mg+2mg.'),
  (21, 'Metformin + Teneligliptin FDC', 'metformin_teneligliptin', 'FDC', 'Biguanide+DPP4i', 'Dynaglipt-M', 'Mankind Pharma Ltd', '₹149/strip of 10 (500mg+20mg)', FALSE, '{"egfr_45_plus": "use", "egfr_below_45": "stop metformin component"}'::jsonb, TRUE, 'neutral', 'low', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/dynaglipt-m-tablet-sr-337936', 'Affordable DPP4i-based FDC. Common Indian prescribing.'),
  (22, 'Metformin + Vildagliptin FDC', 'metformin_vildagliptin', 'FDC', 'Biguanide+DPP4i', 'Ozovil-M', 'Ozone Pharmaceuticals Ltd', '₹70.3/strip of 15 (500mg+50mg)', FALSE, '{"egfr_50_plus": "use", "egfr_below_50": "reduce or stop"}'::jsonb, TRUE, 'neutral', 'low', '["diabetes"]'::jsonb, 'https://www.1mg.com/drugs/ozovil-m-tablet-641750', 'Most prescribed DPP4i-FDC globally.'),
  (23, 'Aspirin', 'aspirin', 'Antiplatelet', 'COX-1 inhibitor', 'Ecosprin', 'USV Private Limited', '₹4.9/strip of 14 (75mg)', TRUE, '{"egfr_all": "use, monitor GI"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular"]'::jsonb, 'https://www.1mg.com/drugs/ecosprin-75-tablet-40765', 'NLEM. ₹4-8/strip. Foundational ACS drug. Loading dose 162-325mg, maintenance 75mg.'),
  (24, 'Clopidogrel', 'clopidogrel', 'Antiplatelet', 'P2Y12 inhibitor', 'Plavix', 'Sanofi', '₹94.8/strip of 14 (75mg)', TRUE, '{"egfr_all": "use, no dose adjustment"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular"]'::jsonb, 'https://www.1mg.com/drugs/plavix-tablet-134976', 'NLEM. Loading 300-600mg. Maintenance 75mg. CYP2C19 variability.'),
  (25, 'Ticagrelor', 'ticagrelor', 'Antiplatelet', 'P2Y12 inhibitor', 'Axcer', 'Sun Pharmaceutical Industries Ltd', '₹427/strip of 14 (60mg)', FALSE, '{"egfr_all": "use, no dose adjustment"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular"]'::jsonb, 'https://www.1mg.com/drugs/axcer-60mg-tablet-416014', 'PLATO trial: preferred over clopidogrel in ACS. Loading 180mg, then 90mg BD.'),
  (26, 'Prasugrel', 'prasugrel', 'Antiplatelet', 'P2Y12 inhibitor', 'Oresugrel', 'Druto Laboratories', '₹98.4/strip of 10 (5mg)', FALSE, '{"egfr_all": "use cautiously"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular"]'::jsonb, 'https://www.1mg.com/drugs/oresugrel-5mg-tablet-593762', 'Avoid >75y, <60kg, prior stroke/TIA. Loading 60mg, maintenance 10mg.'),
  (27, 'Heparin (UFH)', 'heparin', 'Anticoagulant', 'Unfractionated heparin', 'Celhep 25000IU', 'Celon Laboratories Ltd', '₹207/vial (5ml)', TRUE, '{"egfr_all": "use, monitor aPTT"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular"]'::jsonb, 'https://www.1mg.com/drugs/celhep-25000iu-injection-720100', 'NLEM. IV bolus + infusion in ACS. Monitor aPTT 1.5-2.5x baseline.'),
  (28, 'Enoxaparin', 'enoxaparin', 'Anticoagulant', 'LMWH', 'Exhep', 'Emcure Pharmaceuticals Ltd', '₹214/syringe (0.2ml)', FALSE, '{"egfr_30_plus": "1mg/kg SC BD", "egfr_below_30": "1mg/kg OD"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular"]'::jsonb, 'https://www.1mg.com/drugs/exhep-20-injection-301822', 'Weight-based SC. Renal dose adjustment <30.'),
  (29, 'Warfarin', 'warfarin', 'Anticoagulant', 'VKA', 'Warf', 'Cipla Ltd', '₹78.7/strip of 30 (1mg)', TRUE, '{"egfr_all": "use, monitor INR"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular", "atrial_fibrillation", "rheumatic_heart_disease"]'::jsonb, 'https://www.1mg.com/drugs/warf-1-tablet-553037', 'NLEM. Cheap. INR 2-3 most indications, 2.5-3.5 mechanical valves. ONLY anticoagulant safe in valvular/rheumatic AF (DOACs contraindicated).'),
  (30, 'Rivaroxaban', 'rivaroxaban', 'Anticoagulant', 'DOAC - factor Xa', 'Ordiban', 'Cheminnova Life Sciences', '₹229/strip of 7 (10mg)', FALSE, '{"egfr_50_plus": "20mg OD", "egfr_15_50": "15mg OD", "egfr_below_15": "avoid"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular", "atrial_fibrillation"]'::jsonb, 'https://www.1mg.com/drugs/ordiban-tablet-647571', 'Non-valvular AF ONLY. ~₹150/day. CONTRAINDICATED in valvular/rheumatic AF.'),
  (31, 'Apixaban', 'apixaban', 'Anticoagulant', 'DOAC - factor Xa', 'Eliquis', 'Pfizer Ltd', '₹334/strip of 10 (2.5mg)', FALSE, '{"egfr_15_plus": "5mg BD (2.5mg if 2 of: age>=80, weight<=60, Cr>=1.5)", "egfr_below_15": "avoid"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular", "atrial_fibrillation"]'::jsonb, 'https://www.1mg.com/drugs/eliquis-2.5mg-tablet-138240', 'Non-valvular AF ONLY. Lowest bleeding risk among DOACs. ~₹120/day. CONTRAINDICATED in valvular/rheumatic AF.'),
  (32, 'Dabigatran', 'dabigatran', 'Anticoagulant', 'DOAC - direct thrombin', 'Dabitra', 'Emcure Pharmaceuticals Ltd', '₹225/strip (110mg)', FALSE, '{"egfr_30_plus": "150mg BD", "egfr_below_30": "avoid"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular", "atrial_fibrillation"]'::jsonb, 'https://www.1mg.com/drugs/dabitra-110-capsule-408926', 'Non-valvular AF ONLY. Has reversal agent (idarucizumab). GI upset common. CONTRAINDICATED in valvular/rheumatic AF.'),
  (33, 'Streptokinase', 'streptokinase', 'Thrombolytic', 'Fibrinolytic', 'Thromboflux 1500000IU', 'Bharat Serums & Vaccines Ltd', '₹1920/vial (10ml)', TRUE, '{"egfr_all": "use if needed"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular"]'::jsonb, 'https://www.1mg.com/drugs/thromboflux-1500000iu-injection-288098', 'NLEM. KEY INDIAN DRUG. Non-fibrin-specific. 1 hour IV infusion. ~₹5-8K vs Tenecteplase ₹25-35K.'),
  (34, 'Tenecteplase', 'tenecteplase', 'Thrombolytic', 'Fibrinolytic', 'Tenecterel', 'Reliance Life Sciences', '₹29870/vial (30mg)', FALSE, '{"egfr_all": "use if needed"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular"]'::jsonb, 'https://www.1mg.com/drugs/tenecterel-30mg-injection-kit-665741', 'Weight-based single IV bolus. Fibrin-specific. Preferred if affordable.'),
  (35, 'Atorvastatin', 'atorvastatin', 'Statin', 'HMG-CoA reductase inhibitor', 'Xtor', 'Ipca Laboratories Ltd', '₹53.23/strip of 10 (10mg)', TRUE, '{"egfr_all": "no dose adjustment"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular"]'::jsonb, 'https://www.1mg.com/drugs/xtor-10-tablet-114371', 'NLEM. ACS: 80mg load. Maintenance 40-80mg. Cheapest high-intensity statin.'),
  (36, 'Rosuvastatin', 'rosuvastatin', 'Statin', 'HMG-CoA reductase inhibitor', 'Consivas', 'Rosuvastatin', '₹78.7/strip of 10 (5mg)', FALSE, '{"egfr_30_plus": "use", "egfr_below_30": "max 10mg"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular"]'::jsonb, 'https://www.1mg.com/drugs/consivas-5-tablet-31061', 'Higher LDL reduction per mg. Avoid in severe renal impairment.'),
  (37, 'Ramipril', 'ramipril', 'ACE inhibitor', NULL, 'Ziram', 'FDC Ltd', '₹32.5/strip of 10 (2.5mg)', TRUE, '{"egfr_30_plus": "use", "egfr_below_30": "reduce dose, monitor K+"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular", "heart_failure"]'::jsonb, 'https://www.1mg.com/drugs/ziram-2.5-tablet-30210', 'NLEM. First-line post-MI, HF, HTN. Hyperkalemia risk with K+-sparing diuretics.'),
  (38, 'Enalapril', 'enalapril', 'ACE inhibitor', NULL, 'EL', 'Sunij Pharma Pvt Ltd', '₹12.97/strip of 10 (2.5mg)', TRUE, '{"egfr_30_plus": "use", "egfr_below_30": "reduce dose"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular", "heart_failure"]'::jsonb, 'https://www.1mg.com/drugs/el-2.5mg-tablet-266697', 'NLEM. Very cheap. Twice-daily dosing.'),
  (39, 'Telmisartan', 'telmisartan', 'ARB', NULL, 'Telmikind', 'Mankind Pharma Ltd', '₹25.4/strip of 10 (20mg)', TRUE, '{"egfr_all": "use, monitor K+"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular"]'::jsonb, 'https://www.1mg.com/drugs/telmikind-20-tablet-73132', 'NLEM. Long-acting ARB. Hyperkalemia risk.'),
  (40, 'Metoprolol', 'metoprolol', 'Beta blocker', 'Beta-1 selective', 'Metzok', 'USV Private Limited', '₹40.22/strip of 10 (11.8mg)', TRUE, '{"egfr_all": "no dose adjustment"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular", "heart_failure"]'::jsonb, 'https://www.1mg.com/drugs/metzok-12.5-tablet-pr-18452', 'NLEM. Succinate (XL) for HF. Tartrate for ACS. Masks hypoglycemia symptoms.'),
  (41, 'Carvedilol', 'carvedilol', 'Beta blocker', 'Non-selective + alpha-1', 'Carvil', 'Zydus Cadila', '₹65/strip of 10 (3.125mg)', FALSE, '{"egfr_all": "no dose adjustment"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular", "heart_failure"]'::jsonb, 'https://www.1mg.com/drugs/carvil-3.125-tablet-239740', 'Preferred in HFrEF. Titrate slowly. Masks hypoglycemia.'),
  (42, 'Bisoprolol', 'bisoprolol', 'Beta blocker', 'Beta-1 selective', 'bisELECT', 'Intas Pharmaceuticals Ltd', '₹41.72/strip of 10 (2.5mg)', FALSE, '{"egfr_20_plus": "use", "egfr_below_20": "reduce"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular", "heart_failure"]'::jsonb, 'https://www.1mg.com/drugs/biselect-2.5-tablet-48503', 'Once daily. HF mortality benefit (CIBIS-II).'),
  (43, 'Furosemide', 'furosemide', 'Loop diuretic', NULL, 'Lasix', 'Sanofi India Ltd', '₹13.1/strip of 15 (40mg)', TRUE, '{"egfr_all": "use, doses up to 200mg in CKD"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular", "heart_failure"]'::jsonb, 'https://www.1mg.com/drugs/lasix-tablet-69762', 'NLEM. Mainstay diuretic. Monitor K+ Mg++.'),
  (44, 'Spironolactone', 'spironolactone', 'K-sparing diuretic', 'Aldosterone antagonist', 'Aldactone', 'RPG Life Sciences Ltd', '₹34.9/strip of 15 (25mg)', TRUE, '{"egfr_30_plus": "use, monitor K+", "egfr_below_30": "avoid"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular", "heart_failure"]'::jsonb, 'https://www.1mg.com/drugs/aldactone-tablet-116839', 'NLEM. HFrEF mortality benefit (RALES). HYPERKALEMIA RISK with ACEi.'),
  (45, 'Amiodarone', 'amiodarone', 'Antiarrhythmic', 'Class III', 'Tachyra', 'Cipla', '₹65.6/strip of 10 (100mg)', TRUE, '{"egfr_all": "no dose adjustment"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular"]'::jsonb, 'https://www.1mg.com/drugs/tachyra-100-tablet-43493', 'NLEM. Thyroid/lung/liver toxicity. Multiple drug interactions.'),
  (46, 'Digoxin', 'digoxin', 'Cardiac glycoside', NULL, 'Lanoxin', 'Glaxo SmithKline Pharmaceuticals Ltd', '₹13.9/strip of 10 (0.25mg)', TRUE, '{"egfr_50_plus": "0.125-0.25mg", "egfr_below_50": "0.0625-0.125mg, monitor levels"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular", "heart_failure"]'::jsonb, 'https://www.1mg.com/drugs/lanoxin-tablet-39496', 'NLEM. Narrow therapeutic index. Toxicity at low K+/Mg++.'),
  (47, 'Nitroglycerine (Sublingual)', 'ntg_sublingual', 'Nitrate', 'Short-acting', 'Nitroglycerin Controlled Release Tablets', 'Medrock Biotech', '₹190/strip of 30 (2.6mg)', TRUE, '{"egfr_all": "no dose adjustment"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular"]'::jsonb, 'https://www.indiamart.com/proddetail/nitrglycerine-controlled-release-26199997273.html', 'NLEM. SL for acute angina. Caution with SBP <90, sildenafil use.'),
  (48, 'Isosorbide Mononitrate', 'ismn', 'Nitrate', 'Long-acting', 'Monotrate', 'Sun Pharmaceutical Industries Ltd', '₹27.19/strip of 10 (10mg)', TRUE, '{"egfr_all": "no dose adjustment"}'::jsonb, TRUE, 'neutral', '—', '["cardiovascular"]'::jsonb, 'https://www.1mg.com/drugs/monotrate-10-tablet-119000', 'Daily anti-anginal. Need nitrate-free interval to prevent tolerance.');

-- Sync the SERIAL sequence past the highest id
SELECT setval('drugs_id_seq', (SELECT MAX(id) FROM drugs));

-- =================================================================
-- DRUG_INTERACTIONS (30 rows)
-- =================================================================
INSERT INTO drug_interactions (id, drug_a_id, drug_a_name, drug_b_id, drug_b_name,
                               severity, mechanism, clinical_effect, management) VALUES
  (1, 2, 'Glimepiride', NULL, 'Alcohol', 'severe', 'Additive hypoglycemic effect; alcohol impairs gluconeogenesis', 'Severe hypoglycemia, disulfiram-like reaction', 'Avoid alcohol. If consumed, eat carbs, monitor glucose.'),
  (2, 2, 'Glimepiride', 4, 'Glibenclamide', 'severe', 'Both SUs - duplicative therapy', 'Profound hypoglycemia', 'Never combine sulfonylureas.'),
  (3, 1, 'Metformin', NULL, 'IV contrast dye', 'severe', 'Risk of contrast-induced AKI → metformin accumulation → lactic acidosis', 'Lactic acidosis', 'Hold metformin 48h before and after IV contrast if eGFR <60.'),
  (4, 13, 'Pioglitazone', 14, 'Insulin Glargine', 'moderate', 'Additive fluid retention', 'Edema, weight gain, HF exacerbation', 'Monitor for edema. Avoid in HF.'),
  (5, 5, 'Teneligliptin', 2, 'Glimepiride', 'moderate', 'Both lower glucose (additive)', 'Hypoglycemia risk', 'Consider reducing SU dose when adding DPP4i.'),
  (6, 23, 'Aspirin', 25, 'Ticagrelor', 'moderate', 'Standard DAPT - intended combination but bleeding risk', 'Bleeding (GI, intracranial)', 'Standard ACS therapy. PPI if GI risk. Monitor Hb.'),
  (7, 23, 'Aspirin', 30, 'Rivaroxaban', 'severe', 'Combined antiplatelet + anticoagulant', 'Major bleeding risk', 'Use only when essential. Limit duration. Add PPI.'),
  (8, 44, 'Spironolactone', 37, 'Ramipril', 'severe', 'Dual RAAS blockade + K-sparing diuretic', 'HYPERKALEMIA (can be fatal)', 'Monitor K+ at baseline, 1 week, then monthly. Hold if K+ >5.5.'),
  (9, 44, 'Spironolactone', 39, 'Telmisartan', 'severe', 'Dual RAAS + K-sparing', 'Hyperkalemia', 'Monitor K+ closely. Avoid combination in CKD.'),
  (10, 45, 'Amiodarone', 29, 'Warfarin', 'severe', 'Amiodarone inhibits CYP2C9 → reduces warfarin metabolism', 'INR elevation, bleeding', 'Reduce warfarin dose 30-50% when starting amiodarone. Check INR weekly initially.'),
  (11, 45, 'Amiodarone', 46, 'Digoxin', 'severe', 'Amiodarone increases digoxin levels via P-gp inhibition', 'Digoxin toxicity (arrhythmia, GI symptoms)', 'Reduce digoxin dose by 50%. Check digoxin level.'),
  (12, 40, 'Metoprolol', 46, 'Digoxin', 'moderate', 'Additive AV node suppression', 'Bradycardia, AV block', 'Monitor HR, ECG. Use cautiously.'),
  (13, 43, 'Furosemide', 46, 'Digoxin', 'moderate', 'Furosemide-induced hypokalemia potentiates digoxin toxicity', 'Digoxin toxicity', 'Monitor K+ and Mg++. Replete as needed.'),
  (14, 35, 'Atorvastatin', 45, 'Amiodarone', 'moderate', 'Amiodarone inhibits CYP3A4 → increased atorvastatin levels', 'Myopathy, rhabdomyolysis', 'Limit atorvastatin to 20mg max with amiodarone.'),
  (15, 29, 'Warfarin', 23, 'Aspirin', 'severe', 'Combined anticoagulant + antiplatelet', 'Bleeding', 'Only use combination when essential (e.g. mechanical valve + recent stent).'),
  (16, 2, 'Glimepiride', 40, 'Metoprolol', 'moderate', 'Beta blockade masks tachycardia of hypoglycemia', 'Hypoglycemia unawareness', 'Educate patient on non-adrenergic symptoms. Monitor glucose closely.'),
  (17, 2, 'Glimepiride', 41, 'Carvedilol', 'moderate', 'Beta blockade masks hypoglycemia', 'Hypoglycemia unawareness', 'Educate patient. SMBG essential.'),
  (18, 10, 'Empagliflozin', 43, 'Furosemide', 'moderate', 'Additive diuresis', 'Dehydration, hypotension, AKI', 'Reduce furosemide dose by 25-50% when starting SGLT2i. Monitor BP, weight.'),
  (19, 11, 'Dapagliflozin', 44, 'Spironolactone', 'moderate', 'Additive diuresis and electrolyte shifts', 'Volume depletion, electrolyte imbalance', 'Monitor BP, K+, renal function.'),
  (20, 1, 'Metformin', 37, 'Ramipril', 'minor', 'Minor risk of hypoglycemia + lactic acidosis if AKI develops', 'Hyperkalemia, AKI risk in dehydration', 'Monitor K+ and renal function. Hold metformin if dehydrated.'),
  (21, 13, 'Pioglitazone', 37, 'Ramipril', 'moderate', 'Additive fluid retention', 'Edema, HF exacerbation', 'Avoid in HF. Monitor for edema.'),
  (22, 14, 'Insulin Glargine', 41, 'Carvedilol', 'moderate', 'Beta blockade masks hypoglycemia + may prolong recovery', 'Hypoglycemia unawareness, delayed recovery', 'Educate patient. Frequent SMBG. Glucagon available.'),
  (23, 35, 'Atorvastatin', 5, 'Teneligliptin', 'minor', 'No clinically significant interaction', 'Unknown', 'Safe to combine. Standard in T2DM + CVD.'),
  (24, 1, 'Metformin', NULL, 'Alcohol', 'moderate', 'Increased lactic acidosis risk; impairs gluconeogenesis', 'Lactic acidosis, hypoglycemia', 'Limit alcohol. Avoid binge drinking. Patient education.'),
  (25, 23, 'Aspirin', NULL, 'Ibuprofen / Diclofenac (NSAIDs)', 'moderate', 'NSAID blocks aspirin''s antiplatelet effect (competitive COX-1 binding)', 'Reduced cardioprotection + dual GI bleeding risk', 'Avoid concurrent use. If NSAID needed, take aspirin 2h before NSAID.'),
  (26, 35, 'Atorvastatin', NULL, 'Erythromycin / Clarithromycin', 'severe', 'CYP3A4 inhibition → increased statin levels', 'Myopathy, rhabdomyolysis', 'Avoid or hold statin during macrolide course. Use azithromycin instead.'),
  (27, 29, 'Warfarin', NULL, 'Fluconazole', 'severe', 'CYP2C9 inhibition by fluconazole', 'INR elevation, bleeding', 'Reduce warfarin dose. Check INR within 3 days.'),
  (28, 1, 'Metformin', NULL, 'Prednisolone / Steroids', 'moderate', 'Steroids cause hyperglycemia', 'Loss of glycemic control', 'Increase antidiabetic doses during steroid course. Monitor glucose.'),
  (29, 5, 'Teneligliptin', NULL, 'Prednisolone', 'moderate', 'Steroid-induced hyperglycemia', 'Hyperglycemia', 'May need additional agent during steroid course.'),
  (30, 23, 'Aspirin', NULL, 'Alcohol', 'moderate', 'Both irritate gastric mucosa', 'GI bleeding risk', 'Limit alcohol. Use PPI if needed.');

SELECT setval('drug_interactions_id_seq', (SELECT MAX(id) FROM drug_interactions));

-- =================================================================
-- INDIAN_GUIDELINES (29 rows)
-- =================================================================
INSERT INTO indian_guidelines (id, source_id, year, condition, section,
                               recommendation, evidence_level, condition_tags) VALUES
  (1, 'RSSDI', 2022, 'diabetes', 'Diagnosis', 'Diabetes diagnosis: FPG ≥126 mg/dL OR 2-h PG ≥200 mg/dL on 75g OGTT OR HbA1c ≥6.5%. Asymptomatic patients need confirmatory repeat test.', 'A', '["diabetes"]'::jsonb),
  (2, 'RSSDI', 2022, 'diabetes', 'First-line therapy', 'Metformin is first-line at diagnosis combined with lifestyle intervention. If contraindicated: sulfonylurea, TZD, DPP4i, SGLT2i, AGI, or oral GLP-1 RA.', 'A', '["diabetes"]'::jsonb),
  (3, 'RSSDI', 2022, 'diabetes', 'Dual therapy', 'Add SGLT2i, DPP4i, sulfonylurea, TZD, AGI or oral GLP-1 RA when targets not achieved on metformin. Patient-centric choice.', 'A', '["diabetes"]'::jsonb),
  (4, 'RSSDI', 2022, 'diabetes', 'ASCVD/HF/CKD comorbidity', 'In patients with established or high-risk ASCVD, heart failure, diabetic kidney disease, or need for weight loss: prefer SGLT2 inhibitors or GLP-1 RA.', 'A', '["diabetes", "cardiovascular", "heart_failure", "ckd"]'::jsonb),
  (5, 'RSSDI', 2022, 'diabetes', 'Elderly with hypoglycemia risk', 'In elderly patients with increased risk of hypoglycemia, use a DPP4 inhibitor as an alternative to sulfonylurea.', 'A', '["diabetes", "elderly"]'::jsonb),
  (6, 'RSSDI', 2022, 'diabetes', 'HbA1c targets', 'General target HbA1c <7%. Stricter <6.5% for young, no comorbidities. Relaxed 7.5-8% for elderly with comorbidities, hypoglycemia history, or limited life expectancy.', 'A', '["diabetes"]'::jsonb),
  (7, 'RSSDI', 2022, 'diabetes', 'Insulin initiation', 'Initiate insulin in T2DM patients failing three oral agents, with HbA1c >1-1.5% above target, with severe symptomatic hyperglycemia, or in unstable state.', 'A', '["diabetes"]'::jsonb),
  (8, 'RSSDI', 2022, 'diabetes', 'Diet (Indian context)', 'Carbohydrates 50-60% of calories. Prefer complex carbs and low-GI foods. Limit white rice (GI 73); prefer brown rice (GI 68) or millets. Fiber 25-40g/day. Salt <5g/day.', 'A', '["diabetes"]'::jsonb),
  (9, 'RSSDI', 2022, 'diabetes', 'Physical activity', 'Minimum 150 min/week moderate aerobic activity. ≥30 min/day. Resistance training 3x/week. At least 5000 steps/day.', 'A', '["diabetes"]'::jsonb),
  (10, 'RSSDI', 2022, 'diabetes', 'Postprandial hyperglycemia', 'Target PPG <160 mg/dL. AGIs, glinides or SGLT2 inhibitors may be considered for PPG control. Indian diets cause higher PPG due to high-GI traditional foods.', 'A', '["diabetes"]'::jsonb),
  (11, 'RSSDI', 2022, 'diabetes', 'Limited care / resource-constrained', 'In resource-constrained settings: sulfonylurea or metformin or TZDs may be used. Newer SUs (gliclazide) preferred for low cost and reduced hypoglycemia vs older SUs.', 'B', '["diabetes"]'::jsonb),
  (12, 'CSI', 2017, 'cardiovascular', 'STEMI diagnosis', 'Diagnose STEMI based on ECG: ST elevation ≥1mm in 2 contiguous limb leads or ≥2mm in 2 contiguous precordial leads. Troponin (I or T) elevation >99th percentile confirms MI.', 'A', '["cardiovascular"]'::jsonb),
  (13, 'CSI', 2017, 'cardiovascular', 'STEMI primary PCI', 'Primary PCI is preferred reperfusion strategy if door-to-balloon time ≤90 min at PCI-capable center, or ≤120 min from first medical contact at non-PCI center.', 'A', '["cardiovascular"]'::jsonb),
  (14, 'CSI', 2017, 'cardiovascular', 'STEMI fibrinolysis when no PCI', 'If PCI not available within 120 min, give fibrinolysis within 30 min of arrival. Streptokinase (₹5-8K, non-fibrin-specific, 1h infusion) or Tenecteplase (₹25-35K, weight-based bolus, fibrin-specific). Tenecteplase preferred if affordable.', 'A', '["cardiovascular"]'::jsonb),
  (15, 'CSI', 2017, 'cardiovascular', 'STEMI dual antiplatelet', 'Loading: Aspirin 162-325mg PO + P2Y12 inhibitor. Ticagrelor 180mg preferred over Clopidogrel 600mg in ACS (PLATO). Continue DAPT 12 months post-ACS.', 'A', '["cardiovascular"]'::jsonb),
  (16, 'CSI', 2017, 'cardiovascular', 'STEMI anticoagulation', 'Anticoagulation in addition to antiplatelets: Unfractionated heparin IV bolus 60 U/kg + infusion, OR Enoxaparin 1 mg/kg SC BD (1 mg/kg OD if eGFR <30).', 'A', '["cardiovascular"]'::jsonb),
  (17, 'CSI', 2017, 'cardiovascular', 'Post-MI medication regimen', 'Post-MI: DAPT (aspirin + P2Y12i) for 12 months, statin (atorvastatin 80mg or rosuvastatin 40mg), beta blocker (carvedilol/metoprolol/bisoprolol), ACEi/ARB (ramipril/telmisartan).', 'A', '["cardiovascular"]'::jsonb),
  (18, 'CSI', 2020, 'cardiovascular', 'STEMI in non-PCI centers', 'In non-PCI capable hospitals: fibrinolysis within 30 min of arrival, then transfer to PCI-capable center within 24h (pharmaco-invasive strategy).', 'A', '["cardiovascular"]'::jsonb),
  (19, 'CSI', 2017, 'cardiovascular', 'Penicillin allergy considerations', 'Penicillin allergy is NOT a contraindication for aspirin, clopidogrel, ticagrelor, heparin, or fibrinolytics. Document allergy for antibiotic prescribing during admission.', 'B', '["cardiovascular"]'::jsonb),
  (20, 'IHRS/CSI', 2018, 'cardiovascular', 'AF stroke risk - CHA2DS2-VASc', 'Calculate CHA2DS2-VASc for non-valvular AF. Score ≥2 men or ≥3 women: oral anticoagulation indicated. Score 1 men or 2 women: consider OAC.', 'A', '["cardiovascular", "atrial_fibrillation"]'::jsonb),
  (21, 'IHRS/CSI', 2018, 'cardiovascular', 'AF anticoagulation choice', 'Non-valvular AF: DOAC (apixaban, rivaroxaban, dabigatran) preferred over warfarin. Valvular (rheumatic) AF or mechanical valve: WARFARIN ONLY (DOACs contraindicated). RHD is common in India.', 'A', '["cardiovascular", "atrial_fibrillation"]'::jsonb),
  (22, 'IHRS/CSI', 2018, 'cardiovascular', 'Triple therapy post-PCI + AF', 'Patients with AF + recent PCI requiring triple therapy: shorten triple therapy duration (1-4 weeks), then drop aspirin → continue P2Y12i + DOAC for up to 12 months, then DOAC alone.', 'A', '["cardiovascular", "atrial_fibrillation"]'::jsonb),
  (23, 'RSSDI+CSI', 2022, 'overlap', 'Diabetes + HFrEF (EF <40%)', 'SGLT2 inhibitor (empagliflozin or dapagliflozin) is first-line: dual benefit for glycemia AND heart failure (EMPEROR-Reduced, DAPA-HF). Use regardless of HbA1c if T2DM + HFrEF.', 'A', '["diabetes", "cardiovascular", "heart_failure"]'::jsonb),
  (24, 'RSSDI+CSI', 2022, 'overlap', 'Diabetes + HF - drugs to AVOID', 'CONTRAINDICATED in HF: Pioglitazone (fluid retention), Saxagliptin (FDA black box - increased HF hospitalization in SAVOR-TIMI). CAUTION: Glimepiride/glibenclamide (hypoglycemia → cardiac events).', 'A', '["diabetes", "heart_failure"]'::jsonb),
  (25, 'RSSDI+CSI', 2022, 'overlap', 'Diabetes + HF + CKD hyperkalemia', 'In T2DM + HF + CKD on ACEi/ARB + spironolactone: monitor K+ at baseline, 1 week, then monthly. Hold spironolactone if K+ >5.5. Adding SGLT2i mitigates hyperkalemia risk.', 'A', '["diabetes", "heart_failure", "ckd"]'::jsonb),
  (26, 'RSSDI', 2022, 'overlap', 'Diabetes + CKD drug choices', 'In T2DM + CKD: SGLT2i (empagliflozin/dapagliflozin) or GLP-1 RA preferred for renoprotection. ACEi/ARB mandatory if albuminuria. Linagliptin if DPP4i needed (no renal dose adjustment).', 'A', '["diabetes", "ckd"]'::jsonb),
  (27, 'RSSDI', 2022, 'overlap', 'Diabetes + NAFLD', 'Pioglitazone has evidence for NASH improvement. SGLT2i emerging data for NAFLD. Both beneficial in fatty liver - but Pioglitazone CONTRAINDICATED if concurrent HF.', 'B', '["diabetes", "nafld"]'::jsonb),
  (28, 'MoHFW_STG', 2022, 'diabetes', 'NLEM essential drugs - diabetes', 'NLEM 2022 includes: Metformin, Glibenclamide, Gliclazide, Glimepiride, Insulin (regular, NPH, premixed 30/70). These are price-controlled and available at Jan Aushadhi.', 'A', '["diabetes"]'::jsonb),
  (29, 'MoHFW_STG', 2022, 'cardiovascular', 'NLEM essential drugs - cardiovascular', 'NLEM 2022 cardiovascular: Aspirin, Clopidogrel, Atorvastatin, Ramipril, Enalapril, Telmisartan, Metoprolol, Atenolol, Furosemide, Spironolactone, Digoxin, Warfarin, Amiodarone, Heparin, Streptokinase, GTN, ISMN.', 'A', '["cardiovascular"]'::jsonb);

SELECT setval('indian_guidelines_id_seq', (SELECT MAX(id) FROM indian_guidelines));

-- =================================================================
-- HOSPITAL_FORMULARY (48 rows)
-- =================================================================
INSERT INTO hospital_formulary (drug_id, in_stock, stock_level, pharmacy_notes) VALUES
  (1, TRUE, 'high', 'Multiple brands. Glyciphage SR most stocked.'),
  (2, TRUE, 'high', 'Amaryl + generics available.'),
  (3, TRUE, 'moderate', 'Diamicron MR primary stock.'),
  (4, TRUE, 'low', 'Older SU - limited stock.'),
  (5, TRUE, 'high', 'Most-prescribed DPP4i locally.'),
  (6, TRUE, 'moderate', 'Branded Januvia + generics.'),
  (7, TRUE, 'moderate', 'Galvus + Galvus Met FDCs.'),
  (8, TRUE, 'moderate', 'Trajenta - preferred for CKD.'),
  (9, FALSE, '—', 'Not preferred due to HF black box. Available on indent.'),
  (10, TRUE, 'high', 'Jardiance widely stocked.'),
  (11, TRUE, 'high', 'Forxiga + generics. First-line for HFrEF.'),
  (12, TRUE, 'low', 'Limited use due to amputation risk.'),
  (13, TRUE, 'moderate', 'FLAG: avoid in HF patients.'),
  (14, TRUE, 'high', 'Lantus + Basalog biosimilar.'),
  (15, TRUE, 'high', 'Mixtard 30/70 - main premixed.'),
  (16, TRUE, 'high', 'Actrapid IV for DKA.'),
  (17, TRUE, 'low', 'Victoza - high cost, low turnover.'),
  (18, TRUE, 'low', 'Trulicity - very expensive.'),
  (19, TRUE, 'moderate', 'Glucobay for postprandial.'),
  (20, TRUE, 'high', 'Glycomet-GP series widely used.'),
  (21, TRUE, 'high', 'Zita Met popular.'),
  (22, TRUE, 'high', 'Galvus Met.'),
  (23, TRUE, 'high', 'Ecosprin 75mg + 150mg in ED.'),
  (24, TRUE, 'high', 'Clopilet + Plavix stocked.'),
  (25, TRUE, 'high', 'Brilinta - first-line ACS antiplatelet.'),
  (26, TRUE, 'moderate', 'Effient - secondary choice.'),
  (27, TRUE, 'high', 'Standard ACS anticoagulation in ED/CCU.'),
  (28, TRUE, 'high', 'Clexane prefilled syringes available.'),
  (29, TRUE, 'high', 'Warf - cheap, INR clinic available.'),
  (30, TRUE, 'high', 'Xarelto + generics for non-valvular AF.'),
  (31, TRUE, 'moderate', 'Eliquis - preferred in elderly/bleeding risk.'),
  (32, TRUE, 'moderate', 'Pradaxa - reversal agent available (Praxbind).'),
  (33, TRUE, 'high', 'CRITICAL: stocked for thrombolysis. ~₹5-8K.'),
  (34, TRUE, 'moderate', 'TNKase - higher cost option. Single bolus.'),
  (35, TRUE, 'high', 'ACS loading dose 80mg available.'),
  (36, TRUE, 'high', 'Rozavel + generics.'),
  (37, TRUE, 'high', 'Cardace - first-line for HF/post-MI.'),
  (38, TRUE, 'high', 'Enam - cheap NLEM alternative.'),
  (39, TRUE, 'high', 'Telma - widely prescribed ARB.'),
  (40, TRUE, 'high', 'Metolar XL (succinate) for HF. Tartrate for ACS.'),
  (41, TRUE, 'high', 'Carloc - preferred for HFrEF.'),
  (42, TRUE, 'moderate', 'Concor available.'),
  (43, TRUE, 'high', 'Lasix IV + oral. Foundational diuretic.'),
  (44, TRUE, 'high', 'Aldactone - monitor K+ closely.'),
  (45, TRUE, 'high', 'Cordarone IV + oral. ICU stocked.'),
  (46, TRUE, 'moderate', 'Lanoxin - check levels available.'),
  (47, TRUE, 'high', 'Sorbitrate - ED essential.'),
  (48, TRUE, 'high', 'Monotrate - daily anti-anginal.');

-- =================================================================
-- PATIENTS (6 demo patients from the assessment Setup Guide)
-- =================================================================
INSERT INTO patients (id, patient_label, age, sex, bmi, conditions, medications, allergies, labs, vitals, insurance, income_context) VALUES
  (1, 'Failing Metformin', 48, 'M', 31.1, '["T2DM (3yr)", "HTN (1yr)"]'::jsonb, '[{"drug": "Metformin", "dose": "1g BD"}, {"drug": "Telmisartan", "dose": "40mg OD"}]'::jsonb, '["Sulfonamide (rash)"]'::jsonb, '{"HbA1c": 8.4, "FBS": 168, "Cr": 0.9, "eGFR": 92, "TC": 220, "LDL": 142, "HDL": 38, "TG": 280}'::jsonb, '{"BP": "134/86", "HR": 78}'::jsonb, '{"provider": "Star Health Gold", "notes": "Generic covered, branded need pre-auth, \u20b95K/month cap"}'::jsonb, 'Middle-class salaried'),
  (2, 'Complex with CKD', 62, 'F', 27.2, '["T2DM (12yr)", "CKD 3b", "HTN", "Proliferative Retinopathy", "Neuropathy"]'::jsonb, '[{"drug": "Metformin", "dose": "500mg BD"}, {"drug": "Glimepiride", "dose": "2mg OD"}, {"drug": "Atorvastatin", "dose": "20mg HS"}, {"drug": "Telmisartan", "dose": "80mg OD"}, {"drug": "Aspirin", "dose": "75mg OD"}, {"drug": "Pregabalin", "dose": "75mg BD"}]'::jsonb, '["NKDA"]'::jsonb, '{"HbA1c": 9.2, "Cr": 1.8, "eGFR": 32, "K": 4.9, "UrineACR": 380}'::jsonb, '{"BP": null, "HR": null}'::jsonb, '{"provider": "New India Assurance", "notes": "\u20b93L cap, mostly exhausted"}'::jsonb, 'Pension/family support'),
  (3, 'Auto-Driver', 34, 'M', 35.3, '["T2DM (2mo, newly diagnosed)", "Obesity", "NAFLD"]'::jsonb, '[{"drug": "Metformin", "dose": "500mg BD (just started)"}]'::jsonb, '["NKDA"]'::jsonb, '{"HbA1c": 8.8, "FBS": 186, "ALT": 68, "Cr": 0.8, "eGFR": 108, "TG": 320, "HDL": 32}'::jsonb, '{"BP": null, "HR": null}'::jsonb, '{"provider": "NONE", "notes": "No insurance"}'::jsonb, 'Auto-rickshaw driver, daily wage ₹800-1000'),
  (4, 'Acute STEMI', 52, 'M', 26.8, '["Acute chest pain \u00d7 2hrs", "Smoker 20 pack-years", "Family hx father MI at 50"]'::jsonb, '[]'::jsonb, '["Penicillin (ANAPHYLAXIS - 2020)"]'::jsonb, '{"Troponin": 12.4, "Cr": 1.0, "eGFR": 84, "K": 4.2, "Glucose": 142, "ECG": "ST elevation V1-V4 (anterior STEMI)"}'::jsonb, '{"HR": 108, "BP": "95/62", "SpO2": 93, "RR": 24}'::jsonb, '{"provider": "ESI", "notes": "Covers emergency"}'::jsonb, 'ESI-covered worker'),
  (5, 'Post-MI + New AF', 66, 'M', 28.4, '["Anterior MI (3mo ago, DES to LAD)", "T2DM", "HTN", "Newly detected AF"]'::jsonb, '[{"drug": "Aspirin", "dose": "75mg"}, {"drug": "Ticagrelor", "dose": "90mg BD"}, {"drug": "Atorvastatin", "dose": "80mg"}, {"drug": "Ramipril", "dose": "5mg"}, {"drug": "Metoprolol", "dose": "25mg BD"}, {"drug": "Metformin", "dose": "1g BD"}]'::jsonb, '["NKDA"]'::jsonb, '{"HbA1c": 7.4, "Cr": 1.1, "eGFR": 68, "K": 4.4}'::jsonb, '{"HR": "88 (irregularly irregular)", "BP": "128/78"}'::jsonb, '{"provider": "CGHS", "notes": "Covers most drugs"}'::jsonb, 'Retired government employee'),
  (6, 'Diabetes + Heart Failure', 58, 'F', 30.2, '["T2DM (8yr)", "Heart Failure (EF 30%)", "HTN", "CKD 3a"]'::jsonb, '[{"drug": "Metformin", "dose": "500mg BD"}, {"drug": "Glimepiride", "dose": "1mg OD"}, {"drug": "Ramipril", "dose": "10mg OD"}, {"drug": "Carvedilol", "dose": "12.5mg BD"}, {"drug": "Furosemide", "dose": "40mg BD"}, {"drug": "Spironolactone", "dose": "25mg OD"}, {"drug": "Atorvastatin", "dose": "40mg HS"}]'::jsonb, '["NKDA"]'::jsonb, '{"HbA1c": 8.6, "Cr": 1.4, "eGFR": 48, "K": 5.1, "BNP": 850, "Na": 134}'::jsonb, '{"HR": 72, "BP": "110/68", "SpO2": 94}'::jsonb, '{"provider": "Star Health", "notes": "\u20b95K/month cap"}'::jsonb, 'Middle-class with chronic disease costs');

SELECT setval('patients_id_seq', (SELECT MAX(id) FROM patients));

-- =================================================================
-- DONE
-- =================================================================