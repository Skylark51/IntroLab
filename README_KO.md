# IntroLab v0.1 — 설치 및 사용

**환경:** Windows PowerShell, Python 3.10 이상, Git. 분석·저장 기능은 Python 표준 라이브러리 및 SQLite만 사용하므로 별도 유료 서비스가 필요하지 않습니다. Crossref에는 네트워크 연결이 필요합니다.

현재 단계는 문헌 조사와 검증을 돕는 **실행 가능한 CLI 기반 골격**입니다. ChatGPT 자동 로그인, 출판사 원문 자동 판독, 신규성 자동 확정, 완성 논문 자동 생성은 구현되지 않았습니다.

## 1. 로컬 설치 (최초 1회)

PowerShell에서 아래 명령을 실행합니다. 폴더가 이미 존재하고 내용이 있다면 먼저 Git 저장소인지 확인하고 기존 파일을 보존해야 합니다.

~~~powershell
cd "D:\이영섭\01_연구\01_계산화학\AfterPhD\논문자동화"
git clone https://github.com/Skylark51/IntroLab.git IntroLab
cd .\IntroLab
py -3 -m pip install -e .
py -3 -m introlab init
py -3 -m introlab --help
~~~

명령줄에서 introlab 명령을 직접 사용할 수 있는 환경이라면 이후 py -3 -m introlab을 introlab으로 바꾸어도 됩니다.

## 2. 연구 배치 검색

JACS 논문 중 Mn(III)–peroxo 연구 후보 10건을 먼저 모읍니다. 이 단계는 Crossref 검색으로서 논문 내용에 대한 검증이 아닙니다.

~~~powershell
$env:INTRO_CROSSREF_EMAIL = "your-email@example.com"
py -3 -m introlab discover "manganese peroxo ketone reaction" --journal "Journal of the American Chemical Society" --rows 10 --offset 0 --from-year 2020 --to-year 2026
py -3 -m introlab discover "manganese peroxo ketone reaction" --journal "Journal of the American Chemical Society" --rows 10 --offset 10 --from-year 2020 --to-year 2026
py -3 -m introlab paper list
~~~

다른 저널로 반복할 때는 --journal 값만 변경하면 됩니다. 위 email은 반드시 실제 사용할 이메일로 바꿉니다. 지정하지 않아도 검색은 가능하지만 Crossref polite pool 이용을 위해 설정을 권장합니다.

## 3. ChatGPT 웹 브라우징 연계

~~~powershell
py -3 -m introlab prompt --topic "Mn(III)-peroxo 12-MTP vs 14-MTP ring-size effects and ketone nucleophilic attack" --journal "Journal of the American Chemical Society" --out chatgpt_research_prompt.md
~~~

생성된 파일을 **본인의 ChatGPT 웹 검색이 가능한 대화**에 복사해 조사합니다. AI가 반환한 DOI와 원문 내용은 아직 미검증입니다. 현재 버전은 ChatGPT 결과 JSON 자동 수입을 지원하지 않으며 이는 다음 개발 단계입니다.

## 4. DOI와 주장 검증

아래 DOI는 사용법을 위한 예시 표기입니다. 실제 사용 시 Crossref에서 확인한 **실존 DOI**로 교체하십시오. 확인 사실을 기록하기 전에 반드시 직접 출판사 본문 또는 SI를 읽습니다.

~~~powershell
py -3 -m introlab paper add "10.1021/example"
py -3 -m introlab paper check "10.1021/example" --kind publisher --note "Publisher URL, Figure 3, SI Table S2 checked"
py -3 -m introlab claim add "10.1021/example" "Specific mechanistic assertion" --locator "Figure 3 and SI Table S2" --evidence "Brief source-supported note"
py -3 -m introlab claim list
py -3 -m introlab claim review 1 --decision supported --note "Verified against figure and SI"
py -3 -m introlab paper check "10.1021/example" --kind followup --note "Follow-up DOI search and newer studies reviewed"
py -3 -m introlab gap add "Can ring size change the preferred O-O cleavage mechanism?" --dois "10.1021/example"
py -3 -m introlab draft --title "Mn-peroxo introduction"
py -3 -m introlab bibliography --reviewed-only
py -3 -m introlab export --out introlab_export.json
~~~

예시 DOI는 실제 DOI로 등록할 수 없을 수 있습니다. 등록할 수 없는 경우 그 DOI가 없는 것이 정상이며, 임의 데이터로 서지를 만들어서는 안 됩니다.

검증 단계는 서로 별도입니다. M=Crossref DOI/서지 확인, P=출판사 본문 확인, F=후속 연구 검색. 개별 claim은 추가적인 supported 검토가 필요합니다. 이 조건을 모두 충족해야 draft에 나타납니다.

현재 draft 파일은 **근거 기반 Introduction 메모와 참고문헌**입니다. 완성 원고의 자동 문장 생성은 추후 개발합니다. JACS 스타일 또한 최종 투고 전 저널 지침과 비교하여 교정해야 합니다.

## 5. GitHub에 수정사항 커밋/푸시

~~~powershell
git status
git add .
git commit -m "feat: improve literature workflow"
git push origin main
~~~

작업 중인 브랜치가 main이 아닌 경우 해당 브랜치 이름을 사용합니다. 개인 연구 SQLite 파일은 .gitignore에 의해 제외됩니다.

## 6. 로컬 업데이트

~~~powershell
cd "D:\이영섭\01_연구\01_계산화학\AfterPhD\논문자동화\IntroLab"
git status
git pull --ff-only origin main
py -3 -m pip install -e .
py -3 -m introlab --help
~~~

안전한 자동 업데이트 스크립트도 포함되어 있습니다.

~~~powershell
.\scripts\update.ps1
~~~

파일에 커밋되지 않은 변경이 있으면 이 스크립트는 업데이트를 중단합니다. 먼저 git status에서 확인하고 commit 또는 stash합니다. 실제 연구 데이터는 .introlab/research.sqlite3에 저장되며 Git으로 전송하지 않습니다.

## 7. Windows 실행 파일 빌드 및 갱신 (선택)

소스는 Python이고, EXE는 사용 편의를 위한 빌드 산출물입니다.

~~~powershell
.\scripts\build.ps1
.\dist\IntroLab.exe --help
.\scripts\update.ps1 -BuildExe
~~~

최초 build에는 PyInstaller 설치가 필요하며 스크립트가 이를 수행합니다. 또는 GitHub 저장소 → Actions → Build Windows CLI → 성공한 실행 → Artifacts → IntroLab-Windows ZIP을 다운로드하고 IntroLab.exe를 교체할 수 있습니다. GitHub Actions가 정상 실행되어 실제 artifact가 게시된 이후에만 사용할 수 있습니다.

## 8. 오프라인 테스트

~~~powershell
py -3 -m unittest discover -s tests -v
~~~

## v0.2 조사 캠페인

최소 10회 조사, 중복 DOI 제외, ChatGPT JSON 가져오기, 검토 및 한국어 인용 초안은 [WORKFLOW_KO.md](WORKFLOW_KO.md)를 따른다. 기존 근거 노트는 `draft --notes`로 생성한다.

## 주의 및 확장

API 키를 저장하거나 유료 API를 호출하지 않습니다. v0.2는 수동 JSON 가져오기, 기전 공백 평가 및 CLI 문장 편집을 지원합니다. 자동 의미 검증, 조사 이력 시각화, Zotero/CSL 변환은 추후 구현 대상입니다.
