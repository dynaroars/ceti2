public class TCasGood {
     public static void main (String[] args) {
          mainQ(Integer.parseInt(args[0]), Integer.parseInt(args[1]), Integer.parseInt(args[2]));
     }
     
     public static int mainQ(int in,int up, int down) {
	  int bias, r;
	  if (in!=0)
	       bias = up + 100;
	  else
	       bias = up;
	  if (bias > down)
	       r = 1;
	  else
	       r = 0;
	  return r;
     }
}

