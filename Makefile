OCAML_OPTIONS = \
  -I $(CIL173)/_build/src \
  -I $(CIL173)/_build/src/ext \
  -I $(CIL173)/_build/src/frontc \
  -I $(CIL173)/_build/ocamlutil \

OCAMLC =        ocamlc                          $(OCAML_OPTIONS)
OCAMLOPT =      ocamlopt                        $(OCAML_OPTIONS)
OCAMLDEP =      ocamldep                        $(OCAML_OPTIONS)
OCAMLLEX =      ocamllex 

all: coverage.exe preproc.exe instr.exe spy.exe modify.exe

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

preproc.exe: $(PREPROC_MODULES:.cmo=.cmx)
		$(OCAMLOPT) -o $@ unix.cmxa str.cmxa nums.cmxa cil.cmxa $^


COVERAGE_MODULES = \
	common.cmo \
	coverage.cmo \

coverage.exe: $(COVERAGE_MODULES:.cmo=.cmx)
		$(OCAMLOPT) -o $@ unix.cmxa str.cmxa nums.cmxa cil.cmxa $^


INSTR_MODULES = \
	common.cmo \
	instr.cmo \

instr.exe: $(INSTR_MODULES:.cmo=.cmx)
	$(OCAMLOPT) -o $@ unix.cmxa str.cmxa nums.cmxa cil.cmxa $^


SPY_MODULES = \
	common.cmo \
	modtemplate.cmo\
	spy.cmo \

spy.exe: $(SPY_MODULES:.cmo=.cmx)
	$(OCAMLOPT) -o $@ unix.cmxa str.cmxa nums.cmxa cil.cmxa $^


MODIFY_MODULES = \
	common.cmo \
	modtemplate.cmo\
	modify.cmo \

modify.exe: $(MODIFY_MODULES:.cmo=.cmx)
	$(OCAMLOPT) -o $@ unix.cmxa str.cmxa nums.cmxa cil.cmxa $^

clean:
	rm -f *.cmo *.cmi *.d *.cmx *.dx *.o coverage.exe prepro.exe instr.exe spy.exe modify.exe
