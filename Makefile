OCAML_OPTIONS = \
  -I $(CIL173)/_build/src \
  -I $(CIL173)/_build/src/ext \
  -I $(CIL173)/_build/src/frontc \
  -I $(CIL173)/_build/ocamlutil \

OCAMLC =        ocamlc                          $(OCAML_OPTIONS)
OCAMLOPT =      ocamlopt                        $(OCAML_OPTIONS)
OCAMLDEP =      ocamldep                        $(OCAML_OPTIONS)
OCAMLLEX =      ocamllex 

all: coverage preproc

%.cmo: %.ml 
	@if [ -f $*.mli -a ! -f $*.cmi ] ; then $(OCAMLC) -c -g $*.mli ; fi 
	$(OCAMLC) -c -g $*.ml
	@$(OCAMLDEP) $*.ml > $*.d 

%.cmx: %.ml 
	@if [ -f $*.mli -a ! -f $*.cmi ] ; then $(OCAMLC) -c -g $*.mli ; fi 
	$(OCAMLOPT) -c $*.ml
	@$(OCAMLDEP) $*.ml > $*.d 

%.cmi: %.mli
	$(OCAMLC) -c -g $*.mli

%.ml: %.mll
	$(OCAMLLEX) $*.mll

PREPROC_MODULES = \
	common.cmo \
	preproc.cmo \

preproc: $(PREPROC_MODULES:.cmo=.cmx)
		$(OCAMLOPT) -o $@ unix.cmxa str.cmxa nums.cmxa cil.cmxa $^


COVERAGE_MODULES = \
	common.cmo \
	coverage.cmo \

coverage: $(COVERAGE_MODULES:.cmo=.cmx)
		$(OCAMLOPT) -o $@ unix.cmxa str.cmxa nums.cmxa cil.cmxa $^

clean:
	rm -f *.cmo *.cmi *.d *.cmx *.dx *.o coverage prepro
