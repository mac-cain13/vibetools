FasdUAS 1.101.10   ��   ��    k             l     ��  ��    * $ Clean version without debug logging     � 	 	 H   C l e a n   v e r s i o n   w i t h o u t   d e b u g   l o g g i n g   
  
 l     ��  ��    ^ X Save this as an Application with "Stay open after run handler" checked in Script Editor     �   �   S a v e   t h i s   a s   a n   A p p l i c a t i o n   w i t h   " S t a y   o p e n   a f t e r   r u n   h a n d l e r "   c h e c k e d   i n   S c r i p t   E d i t o r      l     ��������  ��  ��        j     �� �� 0 	isrunning 	isRunning  m     ��
�� boovfals      l     ��������  ��  ��        i        I     ������
�� .aevtoappnull  �   � ****��  ��    r         m     ��
�� boovtrue  o      ���� 0 	isrunning 	isRunning      l     ��������  ��  ��        i    
   !   I     ������
�� .miscidlenmbr    ��� null��  ��   ! k    B " "  # $ # Z     % &���� % H      ' ' o     ���� 0 	isrunning 	isRunning & L   	  ( ( m   	 
���� ��  ��   $  ) * ) l   ��������  ��  ��   *  + , + Q   ? - . / - O   6 0 1 0 k   5 2 2  3 4 3 l   �� 5 6��   5 ( " Check multiple security processes    6 � 7 7 D   C h e c k   m u l t i p l e   s e c u r i t y   p r o c e s s e s 4  8 9 8 r     : ; : J     < <  = > = m     ? ? � @ @  c o r e a u t h a >  A B A m     C C � D D  S e c u r i t y A g e n t B  E F E m     G G � H H & A u t h e n t i c a t i o n A g e n t F  I�� I m     J J � K K  l o g i n w i n d o w��   ; o      ���� &0 securityprocesses securityProcesses 9  L M L l     ��������  ��  ��   M  N�� N X    5 O�� P O Q   00 Q R S Q Z   3' T U���� T I  3 ;�� V��
�� .coredoexnull���     **** V 4   3 7�� W
�� 
pcap W o   5 6���� 0 processname processName��   U O   ># X Y X X   E" Z�� [ Z Q   W \ ] ^ \ O   Z _ ` _ k   ^ a a  b c b r   ^ c d e d 1   ^ a��
�� 
titl e o      ���� 0 windowtitle windowTitle c  f g f r   d k h i h n   d i j k j 1   g i��
�� 
pnam k 2   d g��
�� 
butT i o      ���� 0 buttonnames buttonNames g  l m l r   l u n o n I  l s�� p��
�� .corecnte****       **** p 2  l o��
�� 
txtf��   o o      ����  0 textfieldcount textFieldCount m  q r q l  v v��������  ��  ��   r  s t s l  v v�� u v��   u 8 2 Only handle windows with buttons (likely prompts)    v � w w d   O n l y   h a n d l e   w i n d o w s   w i t h   b u t t o n s   ( l i k e l y   p r o m p t s ) t  x�� x Z   v y z���� y ?   v } { | { l  v { }���� } I  v {�� ~��
�� .corecnte****       **** ~ o   v w���� 0 buttonnames buttonNames��  ��  ��   | m   { |����   z k   �    � � � l  � ��� � ���   � ' ! Fill password in any text fields    � � � � B   F i l l   p a s s w o r d   i n   a n y   t e x t   f i e l d s �  � � � Z   � � � ����� � ?   � � � � � o   � �����  0 textfieldcount textFieldCount � m   � �����   � Y   � � ��� � ��� � Q   � � � � � � r   � � � � � m   � � � � � � � 
 a d m i n � n       � � � 1   � ���
�� 
valL � 4   � ��� �
�� 
txtf � o   � ����� 0 i   � R      ������
�� .ascrerr ****      � ****��  ��   � l  � ��� � ���   � ( " Continue if field can't be filled    � � � � D   C o n t i n u e   i f   f i e l d   c a n ' t   b e   f i l l e d�� 0 i   � m   � �����  � o   � �����  0 textfieldcount textFieldCount��  ��  ��   �  � � � l  � ���������  ��  ��   �  � � � l  � ��� � ���   � $  Click positive action buttons    � � � � <   C l i c k   p o s i t i v e   a c t i o n   b u t t o n s �  � � � r   � � � � � J   � � � �  � � � m   � � � � � � � 
 A l l o w �  � � � m   � � � � � � �  O K �  � � � m   � � � � � � �  Y e s �  � � � m   � � � � � � �  C o n t i n u e �  � � � m   � � � � � � �  A c c e p t �  � � � m   � � � � � � �  A u t h o r i z e �  � � � m   � � � � � � � 
 G r a n t �  � � � m   � � � � � � �  P e r m i t �  � � � m   � � � � � � �  A l w a y s   A l l o w �  ��� � m   � � � � � � �  I n s t a l l��   � o      ���� "0 positivebuttons positiveButtons �  � � � l  � ���������  ��  ��   �  ��� � X   � ��� � � Z   �
 � ����� � E  � � � � � o   � ����� 0 buttonnames buttonNames � o   � ����� 0 
buttonname 
buttonName � Z   � � ����� � I  � ��� ���
�� .coredoexnull���     **** � 4   � ��� �
�� 
butT � o   � ����� 0 
buttonname 
buttonName��   � k   � � �  � � � I  � �� ���
�� .prcsclicnull��� ��� uiel � 4   � ��� �
�� 
butT � o   � ����� 0 
buttonname 
buttonName��   �  ��� � l  � � � �  S   � %  Exit after clicking one button    � � � � >   E x i t   a f t e r   c l i c k i n g   o n e   b u t t o n��  ��  ��  ��  ��  �� 0 
buttonname 
buttonName � o   � ����� "0 positivebuttons positiveButtons��  ��  ��  ��   ` o   Z [���� 0 win   ] R      ������
�� .ascrerr ****      � ****��  ��   ^ l �� � ���   � + % Continue if window can't be accessed    � � � � J   C o n t i n u e   i f   w i n d o w   c a n ' t   b e   a c c e s s e d�� 0 win   [ 2  H K��
�� 
cwin Y 4   > B�� �
�� 
pcap � o   @ A���� 0 processname processName��  ��   R R      ������
�� .ascrerr ****      � ****��  ��   S l //�� � ���   � , & Continue if process can't be accessed    � � � � L   C o n t i n u e   i f   p r o c e s s   c a n ' t   b e   a c c e s s e d�� 0 processname processName P o   # $���� &0 securityprocesses securityProcesses��   1 m     � ��                                                                                  sevs  alis    \  Macintosh HD               �<�*BD ����System Events.app                                              �����<�*        ����  
 cu             CoreServices  0/:System:Library:CoreServices:System Events.app/  $  S y s t e m   E v e n t s . a p p    M a c i n t o s h   H D  -System/Library/CoreServices/System Events.app   / ��   . R      ������
�� .ascrerr ****      � ****��  ��   / l >>�� � ���   � &   Continue if System Events fails    � � � � @   C o n t i n u e   i f   S y s t e m   E v e n t s   f a i l s ,  � � � l @@�������  ��  �   �  ��~ � l @B � � � � L  @B � � m  @A�}�}  �   Check every 2 seconds    � � � � ,   C h e c k   e v e r y   2   s e c o n d s�~     � � � l     �|�{�z�|  �{  �z   �  ��y � i     � � � I     �x�w�v
�x .aevtquitnull��� ��� null�w  �v   � k      � �  � � � r        m     �u
�u boovfals o      �t�t 0 	isrunning 	isRunning � �s M     I     �r�q�p
�r .aevtquitnull��� ��� null�q  �p  �s  �y       �o�n�o   �m�l�k�j�m 0 	isrunning 	isRunning
�l .aevtoappnull  �   � ****
�k .miscidlenmbr    ��� null
�j .aevtquitnull��� ��� null
�n boovfals �i �h�g	�f
�i .aevtoappnull  �   � ****�h  �g    	  �f eEc    �e !�d�c
�b
�e .miscidlenmbr    ��� null�d  �c  
 	�a�`�_�^�]�\�[�Z�Y�a &0 securityprocesses securityProcesses�` 0 processname processName�_ 0 win  �^ 0 windowtitle windowTitle�] 0 buttonnames buttonNames�\  0 textfieldcount textFieldCount�[ 0 i  �Z "0 positivebuttons positiveButtons�Y 0 
buttonname 
buttonName   � ? C G J�X�W�V�U�T�S�R�Q�P�O�N ��M�L�K � � � � � � � � � ��J�I�X 
�W 
kocl
�V 
cobj
�U .corecnte****       ****
�T 
pcap
�S .coredoexnull���     ****
�R 
cwin
�Q 
titl
�P 
butT
�O 
pnam
�N 
txtf
�M 
valL�L  �K  �J 

�I .prcsclicnull��� ��� uiel�bCb    kY hO(� �����vE�O�[��l kh  �*�/j 
 �*�/ � �*�-[��l kh  �� �*�,E�O*�-�,E�O*�-j E�O�j j ��j , &k�kh  a *�/a ,FW X  h[OY��Y hOa a a a a a a a a a a vE�O 7�[��l kh �� *��/j 
 *��/j OY hY h[OY��Y hUW X  h[OY�4UY hW X  h[OY��UW X  hOl �H ��G�F�E
�H .aevtquitnull��� ��� null�G  �F     �D
�D .aevtquitnull��� ��� null�E fEc   O)jd*  ascr  ��ޭ