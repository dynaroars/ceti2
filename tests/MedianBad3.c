int mainQ(int x, int y, int z) {
     int m = z;

     if (y < z){
	  if (x<y){
	       m = y;
	  }
	  else 
	       if (x<z){
		    m = x;
	       }
     }
     else{
	  //8
	  if(x>y){
	       //5
	       m=y;
	  }
	  else 
	       //7
	       if (x>z){
		    //6
		    m =x;
	       }
     }

     printf("Middle number is: %d\n",m);
     return m;
}

int main(int argc, char* argv[]){
     int rv = mainQ(atoi(argv[1]), atoi(argv[2]), atoi(argv[2])); //BUG
     return 0;
}

