open Cil
module A = Array				             
module E = Errormsg
module H = Hashtbl
module P = Printf	     
module L = List
module CM = Common	     
module MT = Modtemplate
	      
(* modify statements *)
class modStmtVisitor 
	(sid:int) 
	(mkInstr:instr -> varinfo list ref -> instr list ref -> instr) = 
object (self)

  inherit nopCilVisitor 

  val uks   :varinfo list ref = ref []
  val instrs:instr list ref = ref []
  val mutable status = ""

  method uks    = !uks
  method instrs = !instrs
  method status = status

  method vstmt (s:stmt) = 
    let action (s:stmt): stmt = 
      (match s.skind with 
       |Instr ins when s.sid = sid ->
	 assert (L.length ins = 1);

	 (*CC.ealert "debug: stmt %d\n%a\n" sid dn_stmt s;*)

	 let old_i = L.hd ins in 
	 let new_i = mkInstr old_i uks instrs in	
	 s.skind <- Instr[new_i];

	 status <- (P.sprintf "%s ## %s"  (*the symbol is used when parsing*)
			      (CM.string_of_instr old_i) (CM.string_of_instr new_i));

	 E.log "%s" status

       |_ -> ()
      ); s in
    ChangeDoChildrenPost(s, action)  
end

(*add uk's to function args, e.g., fun(int x, int uk0, int uk1);*)
class funInstrVisitor (uks:varinfo list) = object
  inherit nopCilVisitor

  val ht = H.create 1024 
  method ht = ht

  method vfunc fd = 
    if fd.svar.vname <> "main" then (
      setFormals fd (fd.sformals@uks) ;
      H.add ht fd.svar.vname () 
    );
    DoChildren
end

(*insert uk's as input to all function calls
  e.g., fun(x); -> fun(x,uk0,uk1); *)
class instrCallVisitor (uks:varinfo list) (funsHt:(string,unit) H.t)= object
  inherit nopCilVisitor

  method vinst (i:instr) =
    match i with 
    | Call(lvopt,(Lval(Var(vi),NoOffset)), args,loc) 
	 when H.mem funsHt vi.vname ->
       let uks' = L.map CM.exp_of_vi uks in 
       let i' = Call(lvopt,(Lval(Var(vi),NoOffset)), args@uks',loc) in
       ChangeTo([i'])

    |_ -> SkipChildren
end

let mkMain (mainFd:fundec)
	   (mainQFd:fundec)
	   (correctQFd: fundec)
	   (minps:string list list)
	   (uks:varinfo list)
	   (instrs1:instr list) :stmt list=
  
  (* mainQTyp tmpMainQ;  correctQTyp tmpCorrectQ *)
  let mkTmp fdec =
    let mtyp:typ = match fdec.svar.vtype with 
      |TFun(t,_,_,_) -> t
      |_ -> E.s(E.error "%s is not fun typ %a\n" 
			mainQFd.svar.vname d_type mainQFd.svar.vtype)
    in
    let tmp:lval = var(makeTempVar mainFd mtyp) in 
    let argTyps = L.map (fun vi -> vi.vtype) fdec.sformals in
    mtyp, tmp, argTyps
  in
  
  let mainQTyp, tmpMainQ, argsMainQTyps = mkTmp mainQFd in 
  let correctQTyp, tmpCorrectQ, argsCorrectQTyps = mkTmp correctQFd in 

  let rs =
    let mkInstr (inps:string list) ftyp tmp argTyps = 
      assert (L.length argTyps = L.length inps);	   
      (*tmp = fun(inps);*)
      let args = L.map2 (fun t x -> CM.const_exp_of_string t x)
			argTyps inps in
      CM.mkCall ~ftype:ftyp ~av:(Some tmp) mainQFd.svar.vname args
    in
    
    L.map (fun inps ->
	   let iMainQ = mkInstr inps mainQTyp tmpMainQ argsMainQTyps in 
	   let iCorrectQ = mkInstr inps correctQTyp tmpCorrectQ argsCorrectQTyps in
	   
	   let e:exp = BinOp(Eq, 
			     Lval tmpMainQ, Lval tmpCorrectQ, 
			     CM.boolTyp) in
	   [iMainQ; iCorrectQ], e
	  ) minps in
  
  let instrs2, exps = L.split rs in 
  let instrs2 = L.flatten instrs2 in
		
  (*creates reachability "goal" stmt 
    if(e_1,..,e_n){printf("GOAL: uk0 %d, uk1 %d ..\n",uk0,uk1);klee_assert(0);}
   *)
  let s = L.map (
	      fun uk -> uk.vname ^ (if uk.vtype = intType then " %d" else " %g")
	    ) uks in
  let s = "GOAL: " ^ (String.concat ", " s) ^ "\n" in 
  let print_goal:instr = CM.mkCall "printf" 
				   (Const(CStr(s))::(L.map CM.exp_of_vi uks)) in 
  
  (*klee_assert(0);*)
  let assert_zero:instr = CM.mkCall "klee_assert" [zero] in
  let andExps = MT.applyBinop LAnd exps in
  let reachStmt = mkStmt (Instr([print_goal; assert_zero])) in
  reachStmt.labels <- [Label("ERROR",!currentLoc,false)];
  let ifSkind = If(andExps, mkBlock [reachStmt], mkBlock [], !currentLoc) in
  let instrsSkind:stmtkind = Instr(instrs1@instrs2) in
  [mkStmt instrsSkind; mkStmt ifSkind]

let transform_s = P.sprintf "%s.s%d.%s.ceti.c" (*f.c.s5.z3_c2.ceti.c*)
			    
let transform 
      (astFile:string)
      (inpsFile:string)      
      (sid:CM.sid_t)
      (tplLevel:int)
      (xinfo:string)
      (idxs:int list)
      (maxV:int) =
  
  let ast, mainFd, mainQFd, correctQFd, stmtHt = CM.read_file_bin astFile in
  let minps:string list list  = CM.read_file_bin inpsFile in (*TODO*)
  let cl = L.find(fun cl -> cl#cid = tplLevel) MT.tplCls in
  let mkInstr = cl#mkInstr ast mainFd sid tplLevel maxV idxs xinfo in

  let visitor = (new modStmtVisitor) sid (fun i -> mkInstr i) in
  visitCilFileSameGlobals (visitor:> cilVisitor) ast;
  let stat, uks, instrs = visitor#status, visitor#uks, visitor#instrs in 
  if stat = "" then E.s(E.error "stmt [%d] not modified" sid);
  
  (*modify main*)
  let mainStmts:stmt list = mkMain mainFd mainQFd correctQFd minps uks instrs in
  mainFd.sbody.bstmts <- mainStmts;

  (*add uk's to fun decls and fun calls*)
  let fiv = (new funInstrVisitor) uks in
  visitCilFileSameGlobals (fiv :> cilVisitor) ast;
  visitCilFileSameGlobals ((new instrCallVisitor) uks fiv#ht) ast;

  (*add include "klee/klee.h" to file*)
  ast.globals <- (GText "#include \"klee/klee.h\"") :: ast.globals;
  
  let fn = transform_s ast.fileName sid xinfo in

  (*the symbol is useful when parsing the result, don't mess up this format*)
  E.log "Transform success: ## '%s' ##  %s\n" fn stat;
  CM.writeSrc fn ast


(* main *)			   
let () = begin
    initCIL();
    Cil.lineDirectiveStyle:= None; (*reduce code, remove all junk stuff*)
    Cprint.printLn := false; (*don't print line #*)
    (* for Cil to retain &&, ||, ?: instead of transforming them to If stmts *)
    Cil.useLogicalOperators := true;
    
    let astFile:string = Sys.argv.(1) in
    let inpsFile:string = Sys.argv.(2) in    
    let sid:CM.sid_t = int_of_string Sys.argv.(3) in
    let tplLevel:int = int_of_string Sys.argv.(4) in 
    let xinfo:string = Sys.argv.(5) in
    let idxs:int list = L.map int_of_string (CM.str_split Sys.argv.(6)) in    
    let maxV:int = int_of_string Sys.argv.(7) in
    transform astFile inpsFile sid tplLevel xinfo idxs maxV

end
