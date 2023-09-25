all: doc/ena.pdf

doc/%.pdf:
	python -m hyena.draw -o $*.pdf hyena.$*.System
	pdfcrop $*.pdf $@
	rm -r $*.pdf
	pdftoppm $@ $(@D)/$* -png -f 1 -singlefile
