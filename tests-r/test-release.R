#!/usr/bin/env Rscript
# Host fixtures use temporary files and explicit transport/runtime doubles.
script <- sub("^--file=", "", commandArgs()[startsWith(commandArgs(), "--file=")][[1L]])
root <- normalizePath(file.path(dirname(script), ".."), mustWork = TRUE)
setwd(root)
source('R/sources.R');source('scripts/release.R')
fixture <- tempfile('interface-fixture-');dir.create(fixture)
for(name in c('app/index.html','app/style.css','app/cloud.js','app/lineage.js','app/app.js','app/record.js','app/diagram.json','workflow/jobs.json','workflow/extract-public.sql','LICENSE','THIRD_PARTY.md')) {
 path<-file.path(fixture,name);dir.create(dirname(path),recursive=TRUE,showWarnings=FALSE);stopifnot(file.copy(name,path))
}
for(name in c('R/sources.R','R/inputs.R','R/workflow.R','R/runtime.R','Makefile','scripts/run-workflow.R','scripts/offline.R','OFFLINE.md')) {
 path<-file.path(fixture,name);dir.create(dirname(path),recursive=TRUE,showWarnings=FALSE);writeLines('Invented fixture source',path)
}
dir.create(file.path(fixture,'data'),showWarnings=FALSE)
for(name in c('public-source.json','public-data.json'))stopifnot(file.copy(file.path('data',name),file.path(fixture,'data',name)))
folder<-file.path(fixture,'reference/cpue_a');dir.create(folder,recursive=TRUE)
json_write(list(index=list(1,2),scope='invented fixture'),file.path(folder,'output.json'))
writeLines('<html>Invented fixture report</html>',file.path(folder,'report.html'))
writeBin(charToRaw('%PDF-invented fixture'),file.path(folder,'report.pdf'))
outputs<-setNames(lapply(c('output.json','report.html','report.pdf'),function(name)file_sha256(file.path(folder,name))),c('output.json','report.html','report.pdf'))
record<-list(schema_version=2L,job='cpue_a',signature='invented',analysis_source=list(path='jobs/cpue_a/run.R'),outputs=outputs)
json_write(record,file.path(folder,'record.json'));record<-json_read(file.path(folder,'record.json'))
state<-list(schema_version=2L,settings=list(last_year=2022L),records=list(cpue_a=record),jobs=json_read('workflow/jobs.json')$jobs,last_plan=list(scope='job',start='cpue_a'))
json_write(state,file.path(fixture,'reference/state.json'))
json_write(list(schema_version=2L,images=list()),file.path(fixture,'runtime-catalogue.json'))
# A previous compiled page must be replaced, never copied into a new archive.
writeLines('PREVIOUS_COMPILED_ZIP_MARKER',file.path(fixture,'index.html'))
release_manifest(fixture,verify=FALSE)
raw<-tempfile(fileext='.zip');wrapped<-tempfile(fileext='.zip');release_zip(fixture,raw)
release_saved_bundle(raw,wrapped,'0.0.0-fixture')
restored<-tempfile('interface-restored-');dir.create(restored);release_unpack(wrapped,restored)
extract <- function(path) {
 html<-release_text(path);match<-regmatches(html,regexec('<script id="demo-payload" type="application/json">\\s*(.*?)\\s*</script>',html,perl=TRUE))[[1L]]
 jsonlite::fromJSON(match[[2L]],simplifyVector=FALSE)
}
stopifnot(file.info(file.path(restored,'offline.html'))$size < 300,
  grepl('url=index.html',release_text(file.path(restored,'offline.html')),fixed=TRUE))
payload<-extract(file.path(restored,'index.html'))
stopifnot('bundle'%in%names(payload$saved),is.null(payload$saved$bundle),identical(names(payload$saved$outputs),'cpue_a'))
stopifnot(length(payload$jobs)==22L,payload$cloud$url=='',payload$cloud$data_kind=='public-wcpfc-albacore')
stopifnot(payload$saved$outputs$cpue_a$record$signature=='invented',is.null(payload$example))
stopifnot(identical(charToRaw(payload$saved$outputs$cpue_a$html), readBin(file.path(folder,'report.html'),'raw',n=file.info(file.path(folder,'report.html'))$size)))
stopifnot(identical(digest::digest(charToRaw(payload$saved$outputs$cpue_a$html),algo='sha256',serialize=FALSE),record$outputs[['report.html']]))
stopifnot(!grepl('PREVIOUS_COMPILED_ZIP_MARKER',release_text(file.path(restored,'index.html')),fixed=TRUE))
for(name in c('data.html','data/fiji-source.csv','data/annual-catch.csv','data/extract.sql'))stopifnot(file.exists(file.path(restored,name)))
profile<-json_read(file.path(restored,'data/public-source.json'))
stopifnot(nrow(utils::read.csv(file.path(restored,'data/fiji-source.csv')))==length(profile$sets))
stopifnot(nrow(utils::read.csv(file.path(restored,'data/annual-catch.csv')))==length(profile$catch))
stopifnot(identical(release_text(file.path(restored,'data/extract.sql')),release_text('workflow/extract-public.sql')))
stopifnot(grepl('Masked catch/effort cells are excluded',release_text(file.path(restored,'data.html')),fixed=TRUE))
receipt<-json_read(file.path(restored,'INTERFACE.json'))
stopifnot(!receipt$bundle_embedded,identical(receipt$output_sha256,file_sha256(file.path(restored,'index.html'))))
for(name in names(receipt$source_files))stopifnot(identical(receipt$source_files[[name]],file_sha256(file.path(restored,name))))
stopifnot(identical(file_sha256(file.path(fixture,'app/app.js')),file_sha256(file.path(restored,'app/app.js'))))
# A public page can offer exactly the finished clean archive, whose own pages have no ZIP.
values<-release_values(restored,state)
encoded<-release_base64(readBin(wrapped,'raw',n=file.info(wrapped)$size))
public<-release_interface(restored,state,values=values,bundle=encoded)
stopifnot(identical(public$payload$saved$bundle,encoded),public$receipt$bundle_embedded,!grepl('\n',encoded,fixed=TRUE))
# Rewrapping a clean bundle does not carry the prior embedded ZIP forward.
again<-tempfile(fileext='.zip');release_saved_bundle(wrapped,again,'0.0.0-fixture')
twice<-tempfile('interface-twice-');dir.create(twice);release_unpack(again,twice)
stopifnot(is.null(extract(file.path(twice,'index.html'))$saved$bundle))
stopifnot(identical(file_sha256(file.path(twice,'index.html')),file_sha256(file.path(restored,'index.html'))))
cat('Shared interface fixtures passed: actual partial references, canonical PDFs, archived-profile data guide/CSV/SQL, raw-source hash receipt, clean archive UI, no previous compiled payload, repeat wrapping, and public download of only the finished clean ZIP. No models, Docker or Quarto executed.\n')
unlink(c(fixture,restored,twice,raw,wrapped,again),recursive=TRUE)

# Portable shares require the full installed dependency closure and local archives.
source('scripts/prepare-offline.R')
installed <- matrix(NA_character_, 3L, 6L, dimnames = list(c('Front', 'Dependency', 'baseOnly'),
  c('Package', 'Version', 'Depends', 'Imports', 'LinkingTo', 'Priority')))
installed[, 'Package'] <- rownames(installed); installed[, 'Version'] <- '1.0'
installed['Front', 'Imports'] <- 'Dependency'; installed['Dependency', 'Imports'] <- 'baseOnly'
installed['baseOnly', 'Priority'] <- 'base'
stopifnot(identical(offline_package_order('Front', installed)$order, c('Dependency', 'Front')))
reject <- function(action) inherits(tryCatch(force(action), error = identity), 'error')
stopifnot(reject(offline_package_order('Missing', installed)))
cyclic <- installed; cyclic['Dependency', 'Imports'] <- 'Front'
stopifnot(reject(offline_package_order('Front', cyclic)))
cache <- tempfile('package-cache-'); destination <- tempfile('package-sources-'); dir.create(cache)
stopifnot(reject(offline_package_sources(cache, destination, packages = 'Front', installed = installed)))
installer <- tempfile(fileext = '.R'); offline_install_script(installer, strrep('a', 64L))
invisible(parse(installer))
stopifnot(any(grepl('repos = NULL', readLines(installer), fixed = TRUE)))
unlink(c(cache, destination, installer), recursive = TRUE)
cat('Portable package closure, missing-source and offline installer fixtures passed.\n')
