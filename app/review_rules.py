from __future__ import annotations

from typing import Any, Dict, List, Optional

STATUS_MEETS = "meets_requirement"
STATUS_PARTIAL = "partly_meets_requirement"
STATUS_MISSING = "does_not_meet_requirement"
STATUS_MANUAL = "manual_review_required"
STATUS_NA = "not_applicable"

STATUS_LABELS = {
    STATUS_MEETS: "Meets requirement",
    STATUS_PARTIAL: "Partly meets requirement",
    STATUS_MISSING: "Does not meet requirement",
    STATUS_MANUAL: "Manual review required",
    STATUS_NA: "Not applicable",
}

STATUS_SCORES = {
    STATUS_MEETS: 1.0,
    STATUS_PARTIAL: 0.5,
    STATUS_MISSING: 0.0,
    STATUS_MANUAL: None,
    STATUS_NA: None,
}

CHAPTERS = {
    "A": {"number": 0, "title": "Overall Thesis Coherence", "weight": 15},
    "B": {"number": 1, "title": "Chapter One: Introduction", "weight": 15},
    "C": {"number": 2, "title": "Chapter Two: Literature Review", "weight": 15},
    "D": {"number": 3, "title": "Chapter Three: Research Methods", "weight": 25},
    "E": {"number": 4, "title": "Chapter Four: Results and Discussion", "weight": 15},
    "F": {"number": 5, "title": "Chapter Five: Conclusions and Recommendations", "weight": 10},
    "G": {"number": 0, "title": "Final Submission Readiness", "weight": 5},
}

READINESS_BANDS = [
    (85, "Submission ready", "The reviewed material is broadly coherent and academically defensible."),
    (70, "Ready after minor revision", "Targeted corrections are required before approval."),
    (55, "Major revision required", "Important academic weaknesses must be corrected."),
    (0, "Substantial redevelopment required", "The reviewed material has major omissions or coherence problems."),
]

ACTION_VERBS = [
    "analyse", "analyze", "assess", "compare", "determine", "estimate",
    "evaluate", "examine", "explore", "identify", "investigate", "measure",
    "test", "describe", "establish",
]

def make_rule(
    code: str,
    chapter_key: str,
    section: str,
    item: str,
    headings: List[str],
    evidence_terms: List[str],
    *,
    critical: bool = False,
    applicability: Optional[List[str]] = None,
    adequacy_terms: Optional[List[str]] = None,
    manual_only: bool = False,
) -> Dict[str, Any]:
    return {
        "code": code,
        "chapter_key": chapter_key,
        "chapter_number": CHAPTERS[chapter_key]["number"],
        "chapter_title": CHAPTERS[chapter_key]["title"],
        "section": section,
        "item": item,
        "headings": headings,
        "evidence_terms": evidence_terms,
        "adequacy_terms": adequacy_terms or [],
        "critical": critical,
        "applicability": applicability or ["all"],
        "manual_only": manual_only,
    }

RULES: List[Dict[str, Any]] = [
    # A. Overall thesis coherence
    make_rule("A1","A","Overall Thesis Coherence","The central research problem is clearly stated, specific, and researchable",
              ["statement of the problem","problem statement"],["research problem","problem statement","gap","issue"],critical=True,
              adequacy_terms=["specific","focus","context","population","relationship"]),
    make_rule("A2","A","Overall Thesis Coherence","The background logically leads to the problem without contradiction",
              ["background to the study","statement of the problem"],["background","context","gap","problem"],critical=True,
              adequacy_terms=["therefore","however","against this background","consequently"]),
    make_rule("A3","A","Overall Thesis Coherence","All research objectives are addressed in later chapters",
              ["research objectives","results","summary of findings"],["objective","findings","results"],critical=True,manual_only=True),
    make_rule("A4","A","Overall Thesis Coherence","No new variables, theories, or objectives appear after Chapter One",
              ["research objectives","theoretical review","results"],["variables","theories","objectives"],critical=True,manual_only=True),
    make_rule("A5","A","Overall Thesis Coherence","All recommendations in Chapter Five can be traced to findings in Chapter Four",
              ["results","recommendations"],["finding","recommendation","based on the findings"],critical=True,manual_only=True),

    # B1 Background
    make_rule("B1.1","B","Background to the Study","The discussion moves clearly from global to local context",
              ["background to the study","background of the study"],["global","international","regional","national","local","ghana","context"],
              adequacy_terms=["global","national","local"]),
    make_rule("B1.2","B","Background to the Study","Key concepts and theories relevant to the study are introduced",
              ["background to the study"],["concept","construct","theory","framework","model"]),
    make_rule("B1.3","B","Background to the Study","Relevant empirical evidence is used to justify the context",
              ["background to the study"],["empirical","evidence","studies","reported","found","data","statistics"]),
    make_rule("B1.4","B","Background to the Study","Knowledge gaps are signalled without stating the problem explicitly",
              ["background to the study"],["gap","limited","scarce","few studies","inadequate","unknown"]),
    make_rule("B1.5","B","Background to the Study","The section ends with a clear transition to the problem statement",
              ["background to the study"],["against this background","therefore","hence","this concern","problem"]),

    # B2 Problem
    make_rule("B2.1","B","Statement of the Problem","The problem is clearly articulated and not merely descriptive",
              ["statement of the problem","problem statement"],["problem","challenge","concern","gap","issue"],critical=True,
              adequacy_terms=["despite","yet","however","remains","limited"]),
    make_rule("B2.2","B","Statement of the Problem","Empirical or policy evidence supports the existence of the problem",
              ["statement of the problem"],["empirical","policy","evidence","statistics","report","data"]),
    make_rule("B2.3","B","Statement of the Problem","Weaknesses of existing studies or approaches are explained",
              ["statement of the problem"],["weakness","limitation","previous studies","existing studies","methodological","contextual"]),
    make_rule("B2.4","B","Statement of the Problem","The problem is clearly situated in the study context",
              ["statement of the problem"],["context","setting","ghana","institution","sector","study area"]),
    make_rule("B2.5","B","Statement of the Problem","The problem statement ends with a precise research focus",
              ["statement of the problem"],["this study","seeks to","focuses on","examines","investigates"],critical=True),

    # B3 Purpose, objectives, questions
    make_rule("B3.1","B","Purpose, Objectives, and Research Questions / Hypotheses","The purpose of the study flows directly from the problem",
              ["purpose of the study","statement of the problem"],["purpose of the study","aims to","seeks to"],critical=True),
    make_rule("B3.2","B","Purpose, Objectives, and Research Questions / Hypotheses","Research objectives use measurable action verbs",
              ["research objectives","objectives of the study"],ACTION_VERBS,critical=True),
    make_rule("B3.3","B","Purpose, Objectives, and Research Questions / Hypotheses","Objectives are logically sequenced from general to specific",
              ["research objectives"],["general objective","specific objectives","first","second","third"]),
    make_rule("B3.4","B","Purpose, Objectives, and Research Questions / Hypotheses","Each objective is traceable to a gap identified in the background or problem statement",
              ["background to the study","statement of the problem","research objectives"],["gap","objective","problem","limited"],critical=True,manual_only=True),
    make_rule("B3.5","B","Purpose, Objectives, and Research Questions / Hypotheses","Each objective has a corresponding research question or hypothesis",
              ["research objectives","research questions","research hypotheses"],["objective","research question","hypothesis"],critical=True,manual_only=True),

    # B4
    make_rule("B4.1","B","Significance, Limitations, and Structure","The significance addresses theory, practice, and policy",
              ["significance of the study"],["theory","practice","policy","significance","contribution"],
              adequacy_terms=["theory","practice","policy"]),
    make_rule("B4.2","B","Significance, Limitations, and Structure","Limitations acknowledge genuine constraints without unnecessarily weakening the study",
              ["limitations of the study"],["limitation","constraint","challenge","mitigation"]),
    make_rule("B4.3","B","Significance, Limitations, and Structure","Delimitations clearly define the scope of the study",
              ["delimitations of the study","scope of the study"],["delimitation","scope","boundary","included","excluded"]),
    make_rule("B4.4","B","Significance, Limitations, and Structure","The stated structure of the thesis matches the actual chapters",
              ["organisation of the study","organization of the study"],["chapter one","chapter two","chapter three","chapter four","chapter five"],manual_only=True),

    # C1 Theoretical
    make_rule("C1.1","C","Theoretical Review","Only theories directly relevant to the study are reviewed",
              ["theoretical review","theoretical framework"],["theory","theoretical","framework","relevant"]),
    make_rule("C1.2","C","Theoretical Review","Each theory is explicitly linked to specific objectives",
              ["theoretical review","research objectives"],["theory","objective","supports","explains"],manual_only=True),
    make_rule("C1.3","C","Theoretical Review","Theories logically support the stated hypotheses",
              ["theoretical review","hypotheses development"],["theory","hypothesis","predicts","relationship"],applicability=["quantitative","mixed","sem","econometrics"]),
    make_rule("C1.4","C","Theoretical Review","Key limitations or boundaries of the theories are acknowledged",
              ["theoretical review"],["limitation","boundary","criticism","weakness","assumption"]),
    make_rule("C1.5","C","Theoretical Review","A summary table maps objectives to underpinning theories",
              ["theoretical review"],["summary table","objectives","theories","underpinning"],manual_only=True),

    # C2 Empirical
    make_rule("C2.1","C","Empirical Review","The empirical review is organised by research objectives",
              ["empirical review","review of empirical literature"],["objective","empirical review"],critical=True),
    make_rule("C2.2","C","Empirical Review","Each objective has a dedicated empirical subsection",
              ["empirical review"],["objective one","objective two","objective three","subsection"],manual_only=True),
    make_rule("C2.3","C","Empirical Review","Prior studies’ contexts, methods, and findings are discussed",
              ["empirical review"],["context","method","findings","previous studies","prior studies"],
              adequacy_terms=["context","method","finding"]),
    make_rule("C2.4","C","Empirical Review","Contradictions and weaknesses in prior studies are highlighted",
              ["empirical review"],["contradiction","inconsistent","mixed findings","weakness","limitation"]),
    make_rule("C2.5","C","Empirical Review","Each subsection ends with a clear, study-specific gap",
              ["empirical review"],["gap","limited","therefore","this study","remains unclear"],critical=True),

    # D1 Philosophy
    make_rule("D1.1","D","Research Philosophy, Paradigm, and Approach","The research philosophy is explicitly stated and justified",
              ["research philosophy","research paradigm"],["positivism","interpretivism","pragmatism","critical realism","research philosophy"],
              adequacy_terms=["because","appropriate","justified","suitable"]),
    make_rule("D1.2","D","Research Philosophy, Paradigm, and Approach","The ontological position is stated or clearly implied",
              ["research philosophy"],["ontology","ontological","reality","objectivism","constructivism"]),
    make_rule("D1.3","D","Research Philosophy, Paradigm, and Approach","The epistemological position is stated or clearly implied",
              ["research philosophy"],["epistemology","epistemological","knowledge","objectivist","subjectivist"]),
    make_rule("D1.4","D","Research Philosophy, Paradigm, and Approach","The research approach is stated and justified",
              ["research approach"],["deductive","inductive","abductive","research approach"],
              adequacy_terms=["because","appropriate","justified"]),
    make_rule("D1.5","D","Research Philosophy, Paradigm, and Approach","Research paradigm consistency is demonstrated",
              ["research philosophy","research design"],["paradigm","philosophy","approach","design","methods","analysis"],manual_only=True),
    make_rule("D1.6","D","Research Philosophy, Paradigm, and Approach","Methodological choices are linked directly to research objectives and hypotheses",
              ["research approach","research design","research objectives"],["methodological","objective","hypothesis","linked"],critical=True,manual_only=True),

    # D2 Design
    make_rule("D2.1","D","Research Design and Time Horizon","The research design is clearly stated",
              ["research design"],["quantitative","qualitative","mixed methods","research design"],critical=True),
    make_rule("D2.2","D","Research Design and Time Horizon","The study type is stated",
              ["research design"],["descriptive","explanatory","exploratory","correlational","causal","case study"]),
    make_rule("D2.3","D","Research Design and Time Horizon","The time horizon is stated and justified",
              ["research design"],["cross-sectional","longitudinal","time horizon"],
              adequacy_terms=["because","appropriate","justified"]),
    make_rule("D2.4","D","Research Design and Time Horizon","The unit of analysis is clearly stated",
              ["research design","population"],["unit of analysis","individual","firm","department","institution","household"]),
    make_rule("D2.5","D","Research Design and Time Horizon","The design fits the conceptual framework and hypothesis-testing requirements",
              ["research design","conceptual framework"],["conceptual framework","hypothesis","testing","research design"],critical=True,manual_only=True),

    # D3 Population
    make_rule("D3.1","D","Study Setting, Population, and Sampling Frame","The study setting or context is clearly described and justified",
              ["study area","study setting"],["study area","study setting","context","location"],adequacy_terms=["because","selected","appropriate"]),
    make_rule("D3.2","D","Study Setting, Population, and Sampling Frame","The target population is clearly defined with inclusion and exclusion criteria",
              ["population of the study","target population"],["target population","inclusion criteria","exclusion criteria"],critical=True),
    make_rule("D3.3","D","Study Setting, Population, and Sampling Frame","The sampling frame is described",
              ["sampling frame","population"],["sampling frame","register","list","database","population frame"]),
    make_rule("D3.4","D","Study Setting, Population, and Sampling Frame","Key strata or groups are justified where stratified sampling is used",
              ["sampling technique"],["strata","stratified","groups","proportionate"],applicability=["quantitative","mixed"]),
    make_rule("D3.5","D","Study Setting, Population, and Sampling Frame","Handling of non-response is addressed",
              ["sampling technique","data collection procedure"],["non-response","follow-up","replacement","weighting","response rate"]),

    # D4 Sampling
    make_rule("D4.1","D","Sample Size Determination and Sampling Technique","The sampling technique is clearly stated and justified",
              ["sampling technique"],["probability","non-probability","random","purposive","stratified","sampling technique"],critical=True,
              adequacy_terms=["because","appropriate","justified"]),
    make_rule("D4.2","D","Sample Size Determination and Sampling Technique","The sample-size determination method is stated and justified",
              ["sample size determination","sample size"],["power analysis","yamane","cochran","krejcie","morgan","g*power","formula","sample size"],critical=True,
              adequacy_terms=["because","appropriate","confidence","power","effect size"]),
    make_rule("D4.3","D","Sample Size Determination and Sampling Technique","Sample-size adequacy is linked to the intended analysis",
              ["sample size","data analysis"],["regression","moderation","mediation","sem","analysis","statistical power"],critical=True,
              applicability=["quantitative","mixed","sem","econometrics"]),
    make_rule("D4.4","D","Sample Size Determination and Sampling Technique","Sampling steps are described clearly enough to replicate",
              ["sampling technique"],["step","procedure","selected","sampling interval","random number"]),
    make_rule("D4.5","D","Sample Size Determination and Sampling Technique","Potential sampling bias is acknowledged and mitigations are described",
              ["sampling technique","limitations"],["sampling bias","selection bias","non-response bias","mitigation"]),

    # D5 Instrument
    make_rule("D5.1","D","Data Type, Sources, and Data Collection Instrument","The data type is stated and justified",
              ["data source","data collection instrument"],["primary data","secondary data","data type","mixed data"],adequacy_terms=["because","appropriate","justified"]),
    make_rule("D5.2","D","Data Type, Sources, and Data Collection Instrument","The instrument is clearly described",
              ["data collection instrument"],["questionnaire","interview guide","observation checklist","archival data","document review"]),
    make_rule("D5.3","D","Data Type, Sources, and Data Collection Instrument","The instrument structure is described",
              ["data collection instrument"],["section a","section b","instrument structure","measured","construct"]),
    make_rule("D5.4","D","Data Type, Sources, and Data Collection Instrument","The source of instrument items is stated, with citations where appropriate",
              ["data collection instrument"],["adapted","adopted","developed","scale","items","source"]),
    make_rule("D5.5","D","Data Type, Sources, and Data Collection Instrument","The administration mode is stated and justified",
              ["data collection procedure"],["online","face-to-face","self-administered","interviewer-administered","mixed mode"],adequacy_terms=["because","appropriate","justified"]),

    # D6 Operationalisation
    make_rule("D6.1","D","Operationalisation and Measurement of Variables","Variables are clearly operationalised",
              ["operationalisation of variables","measurement of variables"],["independent variable","dependent variable","moderator","mediator","control variable"],critical=True),
    make_rule("D6.2","D","Operationalisation and Measurement of Variables","Dimensions and indicators for each construct are stated",
              ["operationalisation of variables"],["dimension","indicator","construct","item"]),
    make_rule("D6.3","D","Operationalisation and Measurement of Variables","The measurement scale is specified",
              ["operationalisation of variables"],["likert","nominal","ordinal","interval","ratio","index"]),
    make_rule("D6.4","D","Operationalisation and Measurement of Variables","Control variables are stated and justified",
              ["operationalisation of variables","model specification"],["control variable","age","size","sector","gender","income"],applicability=["quantitative","mixed","sem","econometrics"]),
    make_rule("D6.5","D","Operationalisation and Measurement of Variables","Coding and scoring procedures are described",
              ["operationalisation of variables","data preparation"],["coding","scoring","composite score","reverse coded","index"]),

    # D7 Pilot
    make_rule("D7.1","D","Pilot Testing and Instrument Refinement","A pilot study is reported, including sample, setting, and purpose",
              ["pilot study","pretesting"],["pilot study","pretest","sample","setting","purpose"]),
    make_rule("D7.2","D","Pilot Testing and Instrument Refinement","Changes made after pilot testing are clearly described",
              ["pilot study"],["modified","revised","refined","changes","feedback"]),
    make_rule("D7.3","D","Pilot Testing and Instrument Refinement","Pilot evidence supports the clarity and feasibility of the instrument",
              ["pilot study"],["clarity","feasibility","understood","completion time","feedback"]),

    # D8 Validity/reliability
    make_rule("D8.1","D","Validity and Reliability","The content-validity process is described",
              ["validity and reliability"],["content validity","expert review","pretest"],applicability=["quantitative","mixed","sem"]),
    make_rule("D8.2","D","Validity and Reliability","The construct-validity approach is stated and justified",
              ["validity and reliability"],["construct validity","efa","cfa","factor analysis"],applicability=["quantitative","mixed","sem"]),
    make_rule("D8.3","D","Validity and Reliability","Convergent-validity criteria are stated and assessed where applicable",
              ["validity and reliability"],["convergent validity","average variance extracted","ave","factor loading"],applicability=["sem"]),
    make_rule("D8.4","D","Validity and Reliability","Discriminant-validity criteria are stated and assessed where applicable",
              ["validity and reliability"],["discriminant validity","htmt","fornell","larcker","cross loading"],applicability=["sem"]),
    make_rule("D8.5","D","Validity and Reliability","Reliability tests and thresholds are specified",
              ["validity and reliability"],["cronbach","composite reliability","reliability","threshold"],applicability=["quantitative","mixed","sem"]),
    make_rule("D8.6","D","Validity and Reliability","Results meet thresholds or corrective actions are documented",
              ["validity and reliability","measurement model"],["acceptable","threshold","removed","retained","corrective action"],applicability=["quantitative","mixed","sem"]),

    # D9 Data collection
    make_rule("D9.1","D","Data Collection Procedure","Access and permissions are described",
              ["data collection procedure"],["permission","gatekeeper","approval","access letter"]),
    make_rule("D9.2","D","Data Collection Procedure","The step-by-step data collection process is described",
              ["data collection procedure"],["first","then","thereafter","procedure","administered"]),
    make_rule("D9.3","D","Data Collection Procedure","The data-collection period is stated",
              ["data collection procedure"],["data were collected","between","from","to","weeks","months"]),
    make_rule("D9.4","D","Data Collection Procedure","Response-rate management is described",
              ["data collection procedure"],["response rate","reminder","follow-up","visit"]),
    make_rule("D9.5","D","Data Collection Procedure","Data handling procedures are described",
              ["data collection procedure","ethical considerations"],["storage","anonymisation","anonymization","tracking","password"]),

    # D10 Preparation
    make_rule("D10.1","D","Data Preparation and Assumption Checks","Missing-data treatment is stated",
              ["data preparation","data analysis"],["missing data","listwise deletion","pairwise deletion","imputation","missing values"],applicability=["quantitative","mixed","sem","econometrics"]),
    make_rule("D10.2","D","Data Preparation and Assumption Checks","Outlier detection and treatment are described",
              ["data preparation","data analysis"],["outlier","mahalanobis","z-score","boxplot","winsor"],applicability=["quantitative","mixed","sem","econometrics"]),
    make_rule("D10.3","D","Data Preparation and Assumption Checks","Normality, multicollinearity, and other relevant assumptions are checked",
              ["data preparation","data analysis"],["normality","multicollinearity","vif","tolerance","heteroscedasticity","linearity"],critical=True,
              applicability=["quantitative","mixed","sem","econometrics"]),
    make_rule("D10.4","D","Data Preparation and Assumption Checks","Common-method-bias procedures are addressed where survey data are used",
              ["data preparation","data analysis"],["common method bias","harman","marker variable","procedural remedy"],applicability=["quantitative","mixed","sem"]),

    # D11 Analysis plan
    make_rule("D11.1","D","Data Analysis Plan","Descriptive analyses mapped to Objective 1 are stated clearly",
              ["data analysis"],["descriptive","objective one","frequency","mean","standard deviation"]),
    make_rule("D11.2","D","Data Analysis Plan","Inferential analyses mapped to later objectives are stated clearly",
              ["data analysis"],["inferential","regression","anova","sem","correlation","objective two"],critical=True,
              applicability=["quantitative","mixed","sem","econometrics"]),
    make_rule("D11.3","D","Data Analysis Plan","The hypothesis-testing method and significance criteria are stated",
              ["data analysis"],["hypothesis testing","significance","p-value","alpha","0.05"],critical=True,
              applicability=["quantitative","mixed","sem","econometrics"]),
    make_rule("D11.4","D","Data Analysis Plan","Moderation or mediation testing steps are explained where applicable",
              ["data analysis"],["moderation","mediation","interaction","indirect effect","bootstrapping"],applicability=["quantitative","mixed","sem"]),
    make_rule("D11.5","D","Data Analysis Plan","The model specification is stated, including control variables",
              ["data analysis","model specification"],["model specification","equation","path model","control variable"],applicability=["quantitative","mixed","sem","econometrics"]),
    make_rule("D11.6","D","Data Analysis Plan","The analysis software is stated",
              ["data analysis"],["spss","stata","r software","amos","smartpls","python","eviews","gretl","nvivo","atlas.ti"]),

    # D12 Ethics
    make_rule("D12.1","D","Ethical Considerations","The ethical-clearance source is stated",
              ["ethical considerations"],["ethical clearance","ethics committee","institutional review board","irb","approval"]),
    make_rule("D12.2","D","Ethical Considerations","The informed-consent procedure is described",
              ["ethical considerations"],["informed consent","consent form","voluntary participation"]),
    make_rule("D12.3","D","Ethical Considerations","Confidentiality and anonymity measures are stated",
              ["ethical considerations"],["confidentiality","anonymity","anonymous","privacy"]),
    make_rule("D12.4","D","Ethical Considerations","Data-protection and storage procedures are stated",
              ["ethical considerations"],["data protection","storage","password","encrypted","retention"]),
    make_rule("D12.5","D","Ethical Considerations","Risks to participants and mitigation measures are described",
              ["ethical considerations"],["risk","harm","mitigation","withdraw","minimal risk"]),

    # D13 Summary
    make_rule("D13.1","D","Chapter Summary","The summary restates key methodological choices without introducing new content",
              ["chapter summary","summary"],["methodological","design","sampling","analysis","summary"]),
    make_rule("D13.2","D","Chapter Summary","A clear transition is made to Chapter Four",
              ["chapter summary"],["chapter four","results","findings","next chapter"]),

    # E Results
    make_rule("E1","E","Results and Discussion","Results are presented objective by objective",
              ["results","findings"],["objective","research question","results","findings"],critical=True,manual_only=True),
    make_rule("E2","E","Results and Discussion","Hypothesis decisions are clearly reported where applicable",
              ["hypothesis testing","results"],["hypothesis","supported","not supported","accepted","rejected"],critical=True,
              applicability=["quantitative","mixed","sem","econometrics"]),
    make_rule("E3","E","Results and Discussion","The discussion links findings to theory",
              ["discussion of findings","discussion"],["theory","findings","supports","contradicts","explains"]),
    make_rule("E4","E","Results and Discussion","Findings are compared with previous studies",
              ["discussion of findings"],["previous studies","consistent with","contrary to","similar to","differs from"]),
    make_rule("E5","E","Results and Discussion","Interpretation goes beyond description",
              ["discussion of findings","results"],["implies","suggests","indicates","explains","this means"]),

    # F Conclusions
    make_rule("F1","F","Conclusions and Recommendations","Findings are summarised strictly by objectives",
              ["summary of findings"],["objective","findings","summary"],critical=True,manual_only=True),
    make_rule("F2","F","Conclusions and Recommendations","Conclusions directly address the research problem",
              ["conclusions"],["conclusion","research problem","study established"],critical=True,manual_only=True),
    make_rule("F3","F","Conclusions and Recommendations","Recommendations flow directly from findings",
              ["recommendations"],["recommendation","based on the findings","finding"],critical=True,manual_only=True),
    make_rule("F4","F","Conclusions and Recommendations","Suggestions for future research are linked to limitations",
              ["suggestions for future research","future research"],["future research","limitations","further studies"]),

    # G Final readiness
    make_rule("G1","G","Final Submission Readiness","The thesis follows the required institutional formatting and structure",
              ["organisation of the study","references"],["format","structure","guidelines","chapter"],manual_only=True),
    make_rule("G2","G","Final Submission Readiness","References and citations are consistent and accurate",
              ["references"],["references","citation","apa","harvard","vancouver","chicago"],critical=True,manual_only=True),
    make_rule("G3","G","Final Submission Readiness","The study is internally coherent and defensible",
              ["statement of the problem","research objectives","results","conclusions"],["coherent","aligned","consistent","defensible"],critical=True,manual_only=True),
    make_rule("G4","G","Final Submission Readiness","All methodological choices can be justified",
              ["research methods","methodology"],["justified","appropriate","rationale","methodological choice"],critical=True,manual_only=True),
]


# Exact wording from the official Thesis Self-Evaluation Checklist.
# The expert review layer may provide additional guidance, but these item labels
# must remain unchanged in checklist reports and completed forms.
OFFICIAL_ITEM_TEXT = {
    "A1": "The central research problem is clearly stated, specific, and researchable",
    "A2": "The background logically leads to the problem without contradiction",
    "A3": "All research objectives are addressed in later chapters",
    "A4": "No new variables, theories, or objectives appear after Chapter One",
    "A5": "All recommendations in Chapter Five can be traced to findings in Chapter Four",
    "B1.1": "The discussion moves clearly from global to local context",
    "B1.2": "Key concepts and theories relevant to the study are introduced",
    "B1.3": "Relevant empirical evidence is used to justify the context",
    "B1.4": "Knowledge gaps are signalled without stating the problem explicitly",
    "B1.5": "The section ends with a clear transition to the problem statement",
    "B2.1": "The problem is clearly articulated and not descriptive",
    "B2.2": "Empirical or policy evidence supports the existence of the problem",
    "B2.3": "Weaknesses of existing studies or approaches are explained",
    "B2.4": "The problem is clearly situated in the study context",
    "B2.5": "The problem statement ends with a precise research focus",
    "B3.1": "The purpose of the study flows directly from the problem",
    "B3.2": "Research objectives use measurable action verbs (e.g., analyse, examine)",
    "B3.3": "Objectives are logically sequenced from general to specific",
    "B3.4": "Each objective is traceable to a gap identified in the background/problem statement.",
    "B3.5": "Each objective has a corresponding research question or hypothesis",
    "B4.1": "The significance addresses theory, practice, and policy",
    "B4.2": "Limitations acknowledge genuine constraints without weakening the study",
    "B4.3": "Delimitations clearly define the scope of the study",
    "B4.4": "The stated structure of the thesis matches the actual chapters",
    "C1.1": "Only theories directly relevant to the study are reviewed",
    "C1.2": "Each theory is explicitly linked to specific objectives",
    "C1.3": "Theories logically support the stated hypotheses",
    "C1.4": "Key limitations or boundaries of the theories are acknowledged",
    "C1.5": "A summary table maps objectives to underpinning theories",
    "C2.1": "Empirical review is organised strictly by research objectives",
    "C2.2": "Each objective has a dedicated empirical subsection",
    "C2.3": "Prior studies’ contexts, methods, and findings are discussed",
    "C2.4": "Contradictions and weaknesses in prior studies are highlighted",
    "C2.5": "Each subsection ends with a clear, study-specific gap",
    "D1.1": "The research philosophy is explicitly stated (e.g., positivism, interpretivism, pragmatism) and justified",
    "D1.2": "Ontological position is stated or implied clearly, what reality is assumed in this study",
    "D1.3": "Epistemological position is stated or implied clearly, how knowledge is generated in this study",
    "D1.4": "The research approach is stated (deductive, inductive, abductive) and justified",
    "D1.5": "Research paradigm consistency is demonstrated (narrative or table linking philosophy→approach→design→methods→analysis)",
    "D1.6": "The methodological choices are linked directly to research objectives and hypotheses",
    "D2.1": "The research design is clearly stated (quantitative, qualitative, mixed methods)",
    "D2.2": "The study type is stated (descriptive, explanatory, exploratory, correlational, causal)",
    "D2.3": "The time horizon is stated (cross-sectional or longitudinal) with justification",
    "D2.4": "Unit of analysis is clearly stated (individuals, firms, departments, institutions)",
    "D2.5": "The design fits the conceptual framework and hypothesis testing requirements",
    "D3.1": "Study setting or context is clearly described and justified",
    "D3.2": "Target population is clearly defined with inclusion and exclusion criteria",
    "D3.3": "Sampling frame is described, where the list or access to population comes from",
    "D3.4": "Key strata or groups are justified if stratified sampling is used",
    "D3.5": "Handling of non-response is addressed (follow-ups, replacement, weighting, etc.)",
    "D4.1": "Sampling technique is clearly stated (probability or non-probability) and justified",
    "D4.2": "Sample size determination method is stated and justified (power analysis, formula, rule-of-thumb for SEM/regression)",
    "D4.3": "Sample size adequacy is linked to the intended analysis (regression, moderation, SEM, etc.)",
    "D4.4": "Sampling steps are described clearly enough to replicate",
    "D4.5": "Potential sampling bias is acknowledged and mitigations are described",
    "D5.1": "Data type is stated (primary, secondary, or both) with justification",
    "D5.2": "Instrument is clearly described (questionnaire, interview guide, observation checklist, archival data template)",
    "D5.3": "Instrument structure is described (sections and what each measures)",
    "D5.4": "Source of items is stated (adapted scales, developed items), with citations where appropriate",
    "D5.5": "Administration mode is stated (online, face-to-face, mixed) and justified",
    "D6.1": "Variables are clearly operationalised (IV, DV, moderator/mediator, controls)",
    "D6.2": "Dimensions and indicators for each construct are stated",
    "D6.3": "Measurement scale is specified (Likert type, index, ratio data)",
    "D6.4": "Control variables are stated and justified (firm age, size, sector, etc.)",
    "D6.5": "Coding and scoring procedures are described, including how composite scores are formed",
    "D7.1": "Pilot study is reported, including sample, setting, and purpose",
    "D7.2": "Changes made after pilot testing are described clearly",
    "D7.3": "Evidence from pilot supports clarity and feasibility of instrument",
    "D8.1": "Content validity process is described (expert review, pretest)",
    "D8.2": "Construct validity approach is stated (EFA, CFA) and justified",
    "D8.3": "Convergent validity criteria are stated and assessed where applicable",
    "D8.4": "Discriminant validity criteria are stated and assessed where applicable",
    "D8.5": "Reliability tests are specified (Cronbach alpha, composite reliability) with thresholds",
    "D8.6": "Results meet thresholds or corrective actions are documented",
    "D9.1": "Access and permissions are described (gatekeepers, institutional approvals)",
    "D9.2": "Step-by-step data collection process is described",
    "D9.3": "Time period of data collection is stated",
    "D9.4": "Response rate management is described (reminders, visits, follow-ups)",
    "D9.5": "Data handling procedures are described (storage, anonymisation, tracking)",
    "D10.1": "Missing data treatment is stated (listwise deletion, imputation, etc.)",
    "D10.2": "Outlier detection and treatment are described",
    "D10.3": "Normality, multicollinearity, and other assumptions are checked where relevant",
    "D10.4": "Common method bias steps are addressed where survey data is used",
    "D11.1": "Descriptive analyses mapped to Objective 1 are stated clearly",
    "D11.2": "Inferential analyses mapped to Objectives 2–4 are stated clearly",
    "D11.3": "Hypothesis testing method is stated, including significance criteria",
    "D11.4": "Moderation or mediation testing steps are explained if applicable",
    "D11.5": "Model specification is stated (equations or path model), with control variables",
    "D11.6": "Software used is stated (SPSS, Stata, R, AMOS, SmartPLS, etc.)",
    "D12.1": "Ethical clearance source is stated (department, school, IRB)",
    "D12.2": "Informed consent procedure is described",
    "D12.3": "Confidentiality and anonymity measures are stated",
    "D12.4": "Data protection and storage procedures are stated",
    "D12.5": "Risks to participants are addressed and mitigations described",
    "D13.1": "Summary restates the key methodological choices without new content",
    "D13.2": "Clear transition is made to Chapter Four results and discussion",
    "E1": "Results are presented objective by objective",
    "E2": "Hypotheses are clearly accepted or rejected",
    "E3": "Discussion links findings to theory",
    "E4": "Findings are compared with previous studies",
    "E5": "Interpretation goes beyond description",
    "F1": "Findings are summarised strictly by objectives",
    "F2": "Conclusions directly address the research problem",
    "F3": "Recommendations flow directly from findings",
    "F4": "Suggestions for future research link to limitations",
    "G1": "The thesis follows UCC formatting and structure",
    "G2": "References and citations are consistent and accurate",
    "G3": "The study is internally coherent and defensible",
    "G4": "The student can justify all methodological choices",
}

for _rule in RULES:
    _official = OFFICIAL_ITEM_TEXT.get(_rule["code"])
    if _official:
        _rule["item"] = _official

RULE_BY_CODE = {rule["code"]: rule for rule in RULES}
CRITICAL_RULE_CODES = {rule["code"] for rule in RULES if rule["critical"]}

def is_applicable(rule: Dict[str, Any], research_approach: str) -> bool:
    approach = (research_approach or "all").strip().lower()
    allowed = [str(x).lower() for x in rule.get("applicability", ["all"])]
    return "all" in allowed or approach in allowed

def readiness_band(score: float) -> Dict[str, Any]:
    value = float(score or 0)
    for threshold, label, meaning in READINESS_BANDS:
        if value >= threshold:
            return {"label": label, "meaning": meaning}
    return {"label": READINESS_BANDS[-1][1], "meaning": READINESS_BANDS[-1][2]}
