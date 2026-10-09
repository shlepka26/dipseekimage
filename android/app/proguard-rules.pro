# Python-движок вызывается через Chaquopy (JNI), поэтому стандартная
# оптимизация не должна трогать классы Chaquopy и наш мост.
-keep class com.chaquo.python.** { *; }
-keep class com.dipseek.artist.ArtistBridge { *; }

# org.json используется для обмена с Python
-keep class org.json.** { *; }
