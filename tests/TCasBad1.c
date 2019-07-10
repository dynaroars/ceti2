int buggyQ(int in, int up, int down) {
     int bias, r;
     if (in!=0)
	  bias = up;
     else
	  bias = up;
     if (bias > down)
	  r = 1;
     else
	  r = 0;
     return r;
}


int correctQ(int in, int up, int down){
     return ((in!=0 && (up + 100> down)) || (in==0 && (up > down)));
}

int mainQ(int x, int y, int z){
     int rb = buggyQ(x,y,z);
     int rc = correctQ(x, y, z);
     
     if (rb == rc){
     	  printf("PASS (rb = rc = %d) with input: x %d, y %d, z %d\n",
     		 rc, x, y, z);
	  return 1;
     }
     else{
     	  printf("FAIL (rb %d, rc %d) with input: x %d, y %d, z %d\n",
     		 rb, rc, x, y, z);
	  return 0;
     }
}
int main(int argc, char* argv[]){
     int rv = mainQ(atoi(argv[1]), atoi(argv[2]), atoi(argv[3]));
     return 0;
}

