open Cil
module A = Array				             
module E = Errormsg
module H = Hashtbl
module P = Printf	     
module L = List
module CM = Common	     

type spy_t = CM.sid_t*int*int*int (*sid,cid,level,idx*)
let string_of_spys ((sid,cid,level,idx):spy_t): string =
  P.sprintf "(%d, %d, %d, %d)" sid cid level idx

	    
class findBoolVars (bvs:varinfo list ref) = object
  inherit nopCilVisitor

  method vstmt (s:stmt) = 
    match s.skind with 
    |If(Lval(Var vi,_),_,_,_) -> bvs := vi::!bvs; DoChildren  
    |_->DoChildren

end				       
let findBoolvs fd = 
  let bvs:varinfo list ref = ref [] in
  ignore (visitCilFunction ((new findBoolVars) bvs) fd);
  L.rev !bvs

(** Modify template *)
class virtual
    mtempl (cname:string) (cid:int) (level:int) = object
      val cname = cname
      val cid = cid
      val level = level
      method cname : string = cname
      method cid   : int = cid
      method level : int = level
      method virtual spyStmt : string -> CM.sid_t -> fundec ->
			       (instr -> spy_t option)
      method virtual mkInstr : file -> fundec ->
			       int -> int -> int -> int list -> string -> 
			       (instr -> varinfo list ref ->
				instr list ref -> instr)
    end

							    
(** Const Template:
replace all consts found in an exp to a parameter 
*)
class mtempl_CONSTS cname cid level = object(self)
						      
  inherit mtempl cname cid level as super

  (*returns n, the number of consts found in exp
    This produces 1 template stmt with n params*)
  method spyStmt (filename'':string) (sid:CM.sid_t) (fd:fundec) 
	 : (instr -> spy_t option) = function
    |Set(_,e,_) ->
      let rec findConsts ctr e: int = match e with
	|Const(CInt64 _) -> succ ctr
	|Const(CReal _) -> succ ctr
	|Lval _ -> ctr
	|CastE (_,e1) -> findConsts ctr e1
	|UnOp(_,e1,_) -> findConsts ctr e1
	|BinOp (_,e1,e2,_) -> findConsts ctr e1 + findConsts ctr e2
	| _ ->
	   E.log "%s: can't deal with exp '%a' (sid %d)"
		 super#cname dn_exp e sid;
    	   ctr
      in
      let nConsts:int = findConsts 0 e in
      E.log "%s: found %d consts\n" super#cname nConsts;
      if nConsts > 0 then Some(sid, super#cid, super#level, nConsts)
      else None
    |_ -> None
	    
  (*idxs e.g., [3] means 3 consts found in the susp stmt*)
  method mkInstr (ast:file) (mainFd:fundec) (sid'':int)
		 (tplId'':int) (maxV:int)
		 (idxs:int list) (xinfo:string)
	 : (instr -> varinfo list ref -> instr list ref -> instr) =

    assert (L.length idxs = 1);
    let nConsts = L.hd idxs in
    E.log "** %s: xinfo %s, consts %d\n" super#cname xinfo nConsts;

    fun assignInstr uks instrs -> (
      let mkExp (e:exp): exp =
	let newUk uid uty = CM.mkUk uid uty (-1*maxV) maxV mainFd in
	let ctr = ref (L.length !uks) in

	let rec findConsts e:exp = match e with
	  |Const(CInt64 _) ->
	    let vi, instrs' = newUk !ctr (typeOf e) in 
	    uks := !uks@[vi]; instrs := !instrs@instrs'; incr ctr;
	    CM.exp_of_vi vi
	  |Const(CReal (_,FFloat,_)) ->
	    let vi, instrs' = newUk !ctr (typeOf e) in
	    uks := !uks@[vi]; instrs := !instrs@instrs'; incr ctr; 
	    CM.exp_of_vi vi
	  |Const(CReal (_,FDouble,_)) ->
	    let vi, instrs' = newUk !ctr (typeOf e) in
	    uks := !uks@[vi]; instrs := !instrs@instrs'; incr ctr; 
	    CM.exp_of_vi vi

	  |Lval _ -> e
	  |CastE (ty,e1) -> CastE (ty,findConsts e1)
	  |UnOp (uop,e1,ty) -> UnOp(uop,findConsts e1,ty)
	  |BinOp (bop,e1,e2,ty) -> BinOp(bop,findConsts e1, findConsts e2, ty)

	  | _ ->
	     E.log "%s: don't know how to deal with exp '%a'" super#cname dn_exp e;
	     e
	in
	findConsts e
      in
      
      match assignInstr with
      |Set(v,e,l) -> Set(v, mkExp e, l)
      |_ -> E.s(E.error "unexp assignment instr %a" d_instr assignInstr)
    )
end	    


(*Template for creating parameterized ops*)
class mtempl_OPS_PR cname cid level = object(self)
  inherit mtempl cname cid level as super 
  val opsHt:(binop, binop list) H.t = H.create 128

  val logicBops = [|LAnd; LOr|]
  val compBops =  [|Lt; Gt; Le; Ge; Eq; Ne|]
  val arithBops = [|PlusA; MinusA|]
		    
  initializer
  let ops = [A.to_list logicBops; A.to_list compBops; A.to_list arithBops] in
      L.iter(fun bl -> L.iter (fun b -> H.add opsHt b bl) bl) ops;
      
      E.log "%s: create bops ht (len %d)\n" super#cname (H.length opsHt)
							  
  (*returns n, the number of supported ops in an expression
    This produces n template stmts
   *)
  method spyStmt (filename'':string) (sid:CM.sid_t) (fd:fundec)
	 : (instr -> spy_t option) = function
    |Set(_,e,_) ->
      let rec findOps ctr e: int = match e with
	|Const _ -> ctr
	|Lval _ -> ctr
	|UnOp(_,e1,_) -> findOps ctr e1
	|CastE(_,e1) -> findOps ctr e1
	|BinOp (bop,e1,e2,_) -> 
	  (if H.mem opsHt bop then 1 else 0) + 
	    findOps ctr e1 + findOps ctr e2 

	| _ -> 
	   E.log "%s: don't know how to deal with exp '%a' (sid %d)" 
		 super#cname dn_exp e sid;
    	   ctr
      in
      let nOps:int = findOps 0 e in
      
      E.log "%s: found %d ops\n" super#cname nOps;
      if nOps > 0 then Some(sid, super#cid, super#level, nOps)
      else None
	     
    |_ -> None

  (*apply binary op to a list of exps, e.g, + [v1,..,vn] =>  v1 + .. + vn*)
  method private applyBinop (op:binop) (exps:exp list): exp = 
    assert (L.length exps > 0);
    let e0 = L.hd exps in 
    let ty = typeOf e0 in
    L.fold_left (fun e e' -> BinOp(op,e,e',ty)) e0 (L.tl exps)

  (*
  apply a list of ops, e.g., 
  apply_bops x y + * [v1;v2] [<; =; >] gives
  (v1 * (e1 < e2)) + (v2* (e1 = e2)) + (v3 * (e1 > e2))
   *)
  method private applyBops 
	?(o1:binop=PlusA) ?(o2:binop=Mult) 
	(e1:exp) (e2:exp) 
	(uks:exp list) (ops:binop list) :exp =

    assert (L.length uks > 0);
    assert (L.length uks = L.length ops);
    let ty = typeOf e1 in
    (*E.log "ty of %s is %s\n" (string_of_exp e1) (string_of_typ ty);*)
    assert (L.for_all (fun x -> 
		       (*E.log "ty of %s is %s" (string_of_exp x) (string_of_typ (typeOf x));*)
		       typeOf x = ty) (e2::uks));

    let uk0, uks = L.hd uks, L.tl uks in
    let op0, ops = L.hd ops, L.tl ops in 

    let a = BinOp(o2,uk0,BinOp(op0,e1,e2,ty),ty) in
    let tE = typeOf a in
    L.fold_left2 (fun a op uk ->
		  BinOp(o1,a,BinOp(o2, uk, BinOp (op,e1,e2,ty), ty),tE)
		 ) a ops uks
	       

  (*idxs e.g., [3] means do the 3rd ops found in the susp stmt*)
  method mkInstr (ast'':file) (mainFd:fundec) (sid:int)  
		 (tplId'':int) (maxV:int)
		 (idxs:int list) (xinfo:string) 
	 : (instr -> varinfo list ref -> instr list ref -> instr) = 

    assert (L.length idxs = 1);
    let nthOp:int = L.hd idxs in
    assert (nthOp > 0);
    E.log "** %s: xinfo %s, nth_op %d\n" super#cname xinfo nthOp;

    fun assignInstr uks instrs -> (
      let mkExp (e:exp): exp = 
	let newUk uid = CM.mkUk uid intType 0 1 mainFd in
	let ctr = ref 0 in
	
	let rec findOps e = match e with
	  |Const _ -> e
	  |Lval _ -> e
	  |CastE(ty,e1) -> CastE(ty,findOps e1)
	  |UnOp (uop,e1,ty) -> UnOp(uop,findOps e1,ty)
	  |BinOp (bop,e1,e2,ty) -> 
	    if H.mem opsHt bop then (
	      incr ctr;
	      if !ctr = nthOp then (
		let bops = L.filter (fun op -> op <> bop) (H.find opsHt bop) in
		assert (L.length bops > 0);
		if L.length bops = 1 then
		  BinOp(L.hd bops, e1,e2,ty)
		else(
		  let rs = L.map newUk (CM.range (L.length bops)) in
		  let uks = L.map (fun (vi, instrs') ->
				   uks := !uks@[vi];
				   instrs := !instrs@instrs';
				   CM.exp_of_vi vi
				  ) rs in
		  
		  let xorExp = self#applyBinop BXor uks in		  
		  let assertXor:instr = CM.mkCall "klee_assume" [xorExp] in
		  (* let klee_assert_xor:instr =  *)
		  (*   CC.mkCall "__VERIFIER_assume" [xor_exp] in *)
		  instrs := !instrs@[assertXor];
		  self#applyBops e1 e2 uks bops
		)
	      )
	      else
		BinOp(bop,findOps e1, findOps e2,ty)
	    )
	    else
	      BinOp(bop,findOps e1, findOps e2,ty)

	  | _ -> 
	     E.log "%s: don't know how to deal with exp '%a'" 
		       super#cname dn_exp e;
	     e
	in
	findOps e
      in

      match assignInstr with
      |Set(v,e,l) -> Set(v, mkExp e, l)
      |_ -> E.s(E.error "unexp assignment instr %a" d_instr assignInstr)
    )

end

(** This template changes
typ x = ..;
to 
typ x = uk0 + uk1*v1 + uk2*v2 ; 
where v0 have the same type as x, i.e., typ 
and other vi has type int, i.e., uk_i = {-1,0,1} *)
class mtempl_VS cname cid level = object(self)
  inherit mtempl cname cid level as super

  method private arrStr = P.sprintf "%s.s%d.t%d.arr" (*f.c.s1.t3.arr*)

  (*Supported arithmetic type.  
  Note Cil's isArithmeticType consists of other non-supported (yet) types*)
  method private isMyArithType = function
    |TInt _ -> true
    |TFloat(FFloat,_) -> true
    |TFloat(FDouble,_) -> true
    | _ -> false

  method spyStmt (filename:string) (sid:CM.sid_t) (fd:fundec)
	 : (instr -> spy_t option) = function

    |Set _ ->
      let bvs = findBoolvs fd in (*Find vars in sfd have type bool*)

      (*obtain usuable variables from fd*)
      let vs' = fd.sformals@fd.slocals in
      assert (L.for_all (fun vi -> not vi.vglob) vs');
      (*let vs' = !ST.extra_vars@vs' in*)  (*TODO: Vu*)
      
      let viPred vi =
	self#isMyArithType vi.vtype &&
	  L.for_all (fun bv -> vi <> bv) bvs &&
	    not (CM.in_str "__cil_tmp" vi.vname) &&
	      not (CM.in_str "tmp___" vi.vname)
      in
      let vs = L.filter viPred vs' in
      let nvs = L.length vs in
      
      E.log "%s: found %d/%d avail vars in fun %s [%s]\n"
    	    super#cname nvs (L.length vs') fd.svar.vname
			(String.concat ", " (L.map (fun vi -> vi.vname) vs));
      
      if nvs > 0 then(
	CM.write_file_bin (self#arrStr filename sid super#cid) (A.of_list vs);
	Some(sid, super#cid, super#level, nvs)
      ) else None

    |_ -> None

  method mkInstr (ast:file) (mainFd:fundec) (sid:int)
		 (tplId:int) (maxV:int)
		 (idxs:int list) (xinfo:string)
	 :(instr -> varinfo list ref -> instr list ref -> instr) =

    let vs:varinfo array = CM.read_file_bin (self#arrStr ast.fileName sid tplId) in
    let vs:varinfo list = L.map (fun idx ->  vs.(idx) ) idxs in
    let nvs = L.length vs in

    E.log "** xinfo %s, |vs|=%d, [%s]\n" xinfo nvs
	  (String.concat ", " (L.map (fun vi -> vi.vname) vs));

    fun assignInstr uks instrs -> (
      let mkExp ty: exp =
	let newUk uid uty minV maxV = CM.mkUk uid uty minV maxV mainFd in 
	let n_uks = succ (L.length vs) in
	let rs =
	  L.map (fun uid ->
		 (*uk0 is arbitrary const, other uks are more restricted consts*)
		 match uid with
		 |0 -> (
		   match ty with
		   |TInt _ -> newUk uid ty (-1* maxV) maxV
		   (* |TFloat(FFloat,_) -> newUk uid ty ST.uk_fconst_min ST.uk_fconst_max *)
		   (* |TFloat(FDouble,_) -> newUk uid ty ST.uk_dconst_min ST.uk_dconst_max *)
		   |_ -> E.s(E.error "unexp type %a " dn_type ty)
		 )
		 |_ -> newUk uid intType (-1) 1
		)  (CM.range n_uks)
	in
	let myuks = L.map(fun (vi, instrs') ->
			   uks := !uks@[vi];
			   instrs := !instrs@instrs';
			   CM.exp_of_vi vi
		       )rs in 
	
	let vs = L.map CM.exp_of_vi vs in
	let uk0,uks' = (L.hd myuks), (L.tl myuks) in

	let rexp = L.fold_left2 (fun a x y ->
				 assert (typeOf x = typeOf y);
				 BinOp(PlusA, a, BinOp(Mult, x, y, ty), ty))
				uk0 uks' vs in
	rexp
      in
      
      match assignInstr with
      |Set(v,_,l) -> Set(v, mkExp (typeOfLval v), l)
      |_ -> E.s(E.error "unexp assignment instr %a" d_instr assignInstr)
    )

end

						
let tplCls:mtempl list = 
  [((new mtempl_CONSTS) "CONSTS" 3 1 :> mtempl);
   ((new mtempl_OPS_PR) "OPS_PR" 7 2 :> mtempl);  
   ((new mtempl_VS)     "VS"     1 4 :> mtempl)] 

					    
