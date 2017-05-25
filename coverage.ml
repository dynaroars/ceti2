(*instrument printf stmts to C file*)

open Cil
module E = Errormsg       
module H = Hashtbl
module P = Printf	     
module L = List

let copyObj (x : 'a) = 
  let s = Marshal.to_string x [] in (Marshal.from_string s 0 : 'a)
				      
let writeSrc ?(use_stdout:bool=false)
    (filename:string) (ast:file): unit = 
  let df oc =  dumpFile defaultCilPrinter oc filename ast in
  if use_stdout then df stdout else (
    let fout = open_out filename in
    df fout;
    close_out fout;
    P.printf "write: %s\n" filename
  )
				      
(*** Visitors ***)
  (*Stmts that can be tracked for fault loc and modified for bug fix *)
let can_modify : stmtkind -> bool = function 
  |Instr[Set(_)] -> true
  |_ -> false
	  
class numVisitor ht  = object(self)
  inherit nopCilVisitor

  val mutable mctr = 1
  val mutable cur_fd = None

  method vfunc f = cur_fd <- (Some f); DoChildren

  method vblock b = 
    let action (b: block) : block= 
      let change_sid (s: stmt) : unit = 
	if can_modify s.skind then (
	  s.sid <- mctr;
	  let fd = match cur_fd with 
	    | Some f -> f | None -> E.s(E.error "not in a function") in
	  H.add ht mctr (s, fd);
	  mctr <- succ mctr
	)
	else s.sid <- 0;  (*Anything not considered has sid 0 *)
      in 
      L.iter change_sid b.bstmts; 
      b
    in 
    ChangeDoChildrenPost(b, action)

end
				 
(*Makes every instruction into its own stmt*)
class everyVisitor = object
  inherit nopCilVisitor
  method vblock b = 
    let action (b: block) : block = 
      let change_stmt (s: stmt) : stmt list = 
	match s.skind with
	|Instr(h::t) -> {s with skind = Instr([h])}::L.map mkStmtOneInstr t
	|_ -> [s]
      in
      let stmts = L.flatten (L.map change_stmt b.bstmts) in
      {b with bstmts = stmts}
    in
    ChangeDoChildrenPost(b, action)
end


class breakCondVisitor = object(self)
  inherit nopCilVisitor
  val mutable cur_fd = None
  method vfunc f = cur_fd <- (Some f); DoChildren

  method private mk_stmt s e loc: lval*stmt= 
    let fd = match cur_fd with 
      | Some f -> f | None -> E.s(E.error "not in a function") in
    let v:lval = var(makeTempVar fd (typeOf e)) in
    let i:instr = Set(v,e,loc) in
    v, {s with skind = Instr[i]} 

  method vblock b = 
    let action (b: block) : block = 

      let rec change_stmt (s: stmt) : stmt list = 
	match s.skind with
	(*if (e){b1;}{b2;} ->  int t = e; if (t){b1;}{b2;} *)
	|If(e,b1,b2,loc) -> 
	  let v, s1 = self#mk_stmt s e loc in
	  let s1s = change_stmt s1 in
	  let s2 = mkStmt (If (Lval v,b1,b2,loc)) in
	  let rs = s1s@[s2] in
	    (* if !vdebug then E.log "(If) break %a\n ton%s\n"  *)
	    (*   dn_stmt s (String.concat "\n" (L.map string_of_stmt rs)); *)
	  
	  rs
	    
	(*return e; ->  int t = e; return t;*)
	|Return(Some e,loc) ->
	  let v, s1 = self#mk_stmt s e loc in
	  let s1s = change_stmt s1 in
	  
	  let s2 = mkStmt (Return (Some (Lval v), loc)) in
	  let rs =  s1s@[s2] in
		  (* if !vdebug then E.log "(Return) break %a\nto\n%s\n"  *)
		  (*   dn_stmt s (String.concat "\n" (L.map string_of_stmt rs)); *)
	  
	  rs
	    
	(*x = a?b:c  -> if(a){x=b}{x=c} *)
	|Instr[Set(lv,Question (e1,e2,e3,ty),loc)] ->
	  let i1,i2 = Set(lv,e2,loc), Set(lv,e3,loc) in
	  let sk = If(e1,
		      mkBlock [mkStmtOneInstr i1],
		      mkBlock [mkStmtOneInstr i2], 
		      loc) in
	  let s' = mkStmt sk in
	  let rs = change_stmt s' in 
	  rs
	    
	|_ -> [s]
      in
      let stmts = L.flatten (L.map change_stmt b.bstmts) in
      {b with bstmts = stmts}
    in
    ChangeDoChildrenPost(b, action)
end

(*
  walks over AST and preceeds each stmt with a printf that writes out its sid
  create a stmt consisting of 2 Call instructions
  fprintf "_coverage_fout, sid"; 
  fflush();
 *)
type sid_t = int
let mkVi ?(ftype=TVoid []) fname: varinfo = makeVarinfo true fname ftype
let stderrVi = mkVi ~ftype:(TPtr(TVoid [], [])) "_coverage_fout"
let expOfVi (vi:varinfo): exp = Lval (var vi)
let mkCall ?(ftype=TVoid []) ?(av=None) (fname:string) args : instr = 
  let f = var(mkVi ~ftype:ftype fname) in
  Call(av, Lval f, args, !currentLoc)
      
class coverageVisitor = object(self)
  inherit nopCilVisitor

  method private create_fprintf_stmt (sid : sid_t) :stmt = 
  let str = P.sprintf "%d\n" sid in
  let stderr = expOfVi stderrVi in
  let instr1 = mkCall "fprintf" [stderr; Const (CStr(str))] in 
  let instr2 = mkCall "fflush" [stderr] in
  mkStmt (Instr([instr1; instr2]))
    
  method vblock b = 
    let action (b: block) :block= 
      let insert_printf (s: stmt): stmt list = 
	if s.sid > 0 then [self#create_fprintf_stmt s.sid; s]
	else [s]
      in
      let stmts = L.map insert_printf b.bstmts in 
      {b with bstmts = L.flatten stmts}
    in
    ChangeDoChildrenPost(b, action)
      
  method vfunc f = 
    let action (f: fundec) :fundec = 
      (*print 0 when entering main so we know it's a new run*)
      if f.svar.vname = "main" then (
	f.sbody.bstmts <- [self#create_fprintf_stmt 0] @ f.sbody.bstmts
      );
      f
    in
    ChangeDoChildrenPost(f, action)
end
			  
(* main *)			   
let () = begin
    E.colorFlag := true;

    let src = Sys.argv.(1) in
    let covSrc = Sys.argv.(2) in 
    initCIL();
    Cil.lineDirectiveStyle:= None;  (*reduce code, remove all junk stuff*)

    let ast = Frontc.parse src () in

    (*save orig file*)
    let origSrc = src ^ ".cil.c"in
    writeSrc origSrc ast;


    visitCilFileSameGlobals (new everyVisitor) ast;
    visitCilFileSameGlobals (new breakCondVisitor :> cilVisitor) ast;

    (*add stmt id*)
    let stmtHt = H.create 1024 in
    visitCilFileSameGlobals (new numVisitor stmtHt :> cilVisitor) ast;
    
    (*add printf stmts*)
    visitCilFileSameGlobals (new coverageVisitor) ast;

    (*add to global
    _coverage_fout = fopen("file.c.path", "ab");
     *)

    let newGlobal = GVarDecl(stderrVi, !currentLoc) in 
    ast.globals <- newGlobal::ast.globals;

    let pathFile = covSrc ^ ".path" in
    
    let lhs = var(stderrVi) in
    let arg1 = Const(CStr(pathFile)) in
    let arg2 = Const(CStr("ab")) in
    let instr = mkCall ~av:(Some lhs) "fopen" [arg1; arg2] in
    let newStmt = mkStmt (Instr[instr]) in
    
    let fd = getGlobInit ast in
    fd.sbody.bstmts <- newStmt::fd.sbody.bstmts;
    
    writeSrc covSrc ast
end
