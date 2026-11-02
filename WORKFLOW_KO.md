# IntroLab v0.2 사용 방법

Python 3.10+ 표준 라이브러리와 SQLite를 사용한다. ChatGPT 웹조사는 사용자 계정에서 수행하고 JSON으로 가져온다. 로그인·쿠키·메모리 수집 및 유료 API 자동 호출은 하지 않는다.

## 설치 및 실험실 설정

```powershell
Set-Location 'D:\이영섭\01_연구\01_계산화학\AfterPhD\논문자동화\IntroLab'
py -3 -m pip install -e .
py -3 -m introlab init
Copy-Item examples\project.json .introlab\project.json
notepad .introlab\project.json
py -3 -m introlab project set .introlab\project.json
```

`metals`, `ligands`, `reactions`, `substrates`에 실제 연구 대상을 입력한다. `style_rules`에 실험실 작성 원칙을 추가한다. 알려지지 않은 리간드는 기본값에 넣지 않았다. 선택적으로 `from_year`, `to_year`, `journals`를 설정한다. 실험실 원고 예시가 없는 상태에서 실제 문체를 학습했다고 주장하지 않는다.

## 최소 10회 실제 브라우징

```powershell
py -3 -m introlab campaign plan --rounds 10
py -3 -m introlab campaign prompt 1 --out .introlab\round-01.md
notepad .introlab\round-01.md
```

생성된 프롬프트를 사용자의 ChatGPT에 전달하여 웹조사를 수행한다. `schemas/research-import.schema.json`을 함께 제공하고 JSON 결과를 `.introlab\round-01.json`으로 저장한다. `examples/research-template.json`은 빈 형식 예시다. `papers`에 실제 조사한 5–15편이 없으면 가져오기가 거부된다. 가상의 논문을 예시에 넣지 않았다.

```powershell
py -3 -m introlab import .introlab\round-01.json
py -3 -m introlab review --out .introlab\review.json
notepad .introlab\review.json
py -3 -m introlab campaign review 1 --note '실제 열람 URL과 관련성 및 리간드 후보 포함 여부를 확인함'
py -3 -m introlab campaign prompt 2 --out .introlab\round-02.md
```

이 과정을 10회 이상 순서대로 반복한다. 다음 회차 프롬프트는 직전 가져오기가 끝난 뒤 생성해야 최신 DOI 제외 목록이 반영된다. `campaign list`로 완료 상태를 확인한다. 생성/가져오기만으로 회차가 완료되지는 않는다. 완료는 사용자의 실제 조사 기록 검토에 대한 확인이며 프로그램이 브라우징 행위를 독립적으로 증명하지는 않는다.

신규 발굴에 이미 가져온 DOI가 들어오면 전체 배치를 거부한다. 후속 해결 여부 검증에서는 기존 논문을 다시 읽을 수 있고 `paper check --kind followup` 메모에 기록한다. 리간드 일치 및 과학적 관련성은 사람이 확인해야 한다. Crossref 검색은 후보 메타데이터 수집이며 10회 브라우징에 포함되지 않는다.

## 검증 및 한국어 Introduction

```powershell
py -3 -m introlab paper add '실제 DOI'
py -3 -m introlab paper check '실제 DOI' --kind publisher --note '원문 URL, SI URL, 그림/표/페이지 및 접근 상태'
py -3 -m introlab claim list
py -3 -m introlab claim review 1 --decision supported --note 'claim 1의 문장과 원문 근거가 일치함'
py -3 -m introlab paper check '실제 DOI' --kind followup --note '조사일, 검색식, 기간, 독립 후속논문의 DOI/URL과 해결·반례 여부'
py -3 -m introlab sentence list
py -3 -m introlab sentence review 1 --note '한국어 표현 및 문장 전체가 claim 1로 지지됨을 확인'
py -3 -m introlab draft --title 'Introduction 초안' --out .introlab\introduction.ko.md
```

JSON의 `sentences`로 한국어 문장과 파일 내 claim ID를 함께 가져오거나 `sentence add '문장' --claims 1 2`로 등록한다. 모든 AI 입력은 pending 후보로 저장된다. Crossref 검증·원문 확인·claim 승인·후속 문헌 확인·문장 승인 중 하나라도 빠지면 정식 한국어 초안에 나오지 않는다. 접근 불가 원문, 해석/가설 및 미해결 claim도 사실 서술에서 제외한다. 가설과 공백은 별도 gap 데이터로 보존한다.

`문서경로.citations.json`에 문장→claim→DOI→원문 위치/URL이 저장된다. `sentence edit 1 '수정된 한국어 문장' --claims 1`은 이전 문장을 이력에 보존하고 재승인을 요구한다. `draft`는 저장된 문장을 덮어쓰지 않는다. Markdown을 직접 수정하면 DB에 자동 반영되지 않으므로 `sentence edit`을 사용한다. 번역 생성기는 아직 구현하지 않았으며 한국어 초안을 임의로 번역하지 않는다. 기존 영문 근거 노트는 `draft --notes`로 출력한다.

## 관계, 후보 평가와 기존 결과

```powershell
py -3 -m introlab relation add 2 1 --kind contradicts --note '독립 논문의 상충 경로 및 원문 위치'
py -3 -m introlab gap add '구체적으로 미규명된 TS는 무엇인가?' --dois '실제 DOI'
py -3 -m introlab gap assess 1 .introlab\assessment.json
py -3 -m introlab result add --label '프로젝트 예비 결과' --text '현재까지 확인된 내용과 불확실성' --source '실제 파일 경로 또는 실험 기록 위치'
py -3 -m introlab export --out .introlab\project-export.json
py -3 -m introlab export --resultlab --out .introlab\resultlab.json
```

평가 JSON은 `schemas/gap-assessment.schema.json`을 따른다. 다섯 항목의 점수(0–5) 및 근거, 후속 조사 범위, 실제 문헌 URL, reactant/intermediate/transition_state/irc/spin_states 계획이 필수다. 10개 실제 조사 회차를 검토하기 전에는 `shortlisted` 평가가 거부된다. ResultLab에는 shortlisted 후보만 전달하며 resolved/conflicting 후보는 전달하지 않는다. 점수는 연구자의 평가 기록이며 저널 수준이나 신규성을 보증하지 않는다.

supports/contradicts/supersedes/unresolved는 claim 간 관계로 저장된다. 상충 또는 대체 관계가 있는 사실은 보수적으로 초안에서 제외된다. 관계를 자동 판정하거나 충돌을 해소하는 기능은 아직 없다. 후속 논문은 다른 claim으로 등록하고 관계를 연결한다. 기존 결과는 예비 프로젝트 문맥으로 조사 프롬프트와 ResultLab JSON에 들어가며, 문헌이나 검증된 사실로 자동 승인되지 않는다.

## 업데이트와 Windows 실행 파일

```powershell
git pull --ff-only origin main
py -3 -m pip install -e .
py -3 -m unittest discover -s tests -v
.\scripts\build.ps1
.\dist\IntroLab.exe --help
```

다음부터는 `.\scripts\update.ps1 -BuildExe`로 소스 갱신·설치·테스트·빌드를 수행할 수 있다. Git이 이 D 드라이브에서 dubious ownership을 보고하면, 신뢰하는 이 저장소 경로만 등록한다.

```powershell
git config --global --add safe.directory 'D:/이영섭/01_연구/01_계산화학/AfterPhD/논문자동화/IntroLab'
```

`.introlab` 연구 데이터, 비밀 키, `dist`는 Git에 올리지 않는다. EXE는 `dist\IntroLab.exe`에서 사용하거나 GitHub Actions의 해당 커밋에 대한 성공한 Windows 빌드 artifact를 내려받는다. 실행 시 현재 폴더의 `.introlab`을 사용하므로 항상 프로젝트 폴더에서 실행한다. DB 마이그레이션은 기존 문헌·검토 데이터를 보존하며 중요한 연구 DB는 업데이트 전에 별도 백업한다.

## 현재 범위

수동 ChatGPT 조사 교환, 검증 상태·이력, 한국어 승인 문장 조립과 인용, 후보 평가, 예비 결과 및 ResultLab 내보내기를 구현했다. OpenAlex adapter, 자동 브라우징/API 연동, 의미 기반 기전 판정, CSL/Zotero 스타일 변환, 자동 번역, Gaussian 실행은 아직 구현하지 않았다. JACS 참고문헌은 준용 형식이며 출판 전 편집 검토가 필요하다. 테스트의 가상 데이터는 오프라인 소프트웨어 검증용이고 실제 논문 조사로 간주하지 않는다.
