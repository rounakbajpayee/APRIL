TESTS:
1.1- passed
1.2- the borders of the widget are somewhat blurry, i think that is from having a border which is not matching with the bg or is too thin, maybe we remove the border, not sure. the rest looks crisp
1.3- passed
1.4- passed, timeout ~6 seconds
1.5- passed
1.6- passed
1.7- passed. collapses after ~10 seconds not 7
1.8- voice on/off works. at home yes/no also toggles but does nothing, same for terminal and quit works nicely

2.1- in less than .3 seconds nothing get's recorded, a little longer and it works around .8
2.2- passed
2.3- passed
2.4- passed
2.5- passed
2.6- passed
2.7- actually it says i captured that but cannot process or something and the terminal shows transcript unavailable 

3.1- passed
3.2- i don't think it passed
{"ts": "2026-05-20T09:42:36.313238+00:00", "event": "request_begin", "source": "voice", "request_id": 21}

{"ts": "2026-05-20T09:42:36.365804+00:00", "event": "audio_captured", "duration": 4.952729300013743, "size_kb": 154.0, "request_id": 21}

{"ts": "2026-05-20T09:42:53.527722+00:00", "event": "transcript", "transcript": "hey what's up just testing your local whisper box", "request_id": 21}

{"ts": "2026-05-20T09:42:53.578496+00:00", "event": "user_text", "source": "voice", "text": "hey what's up just testing your local whisper box", "request_id": 21}

{"ts": "2026-05-20T09:42:59.385013+00:00", "event": "intent_plan", "source": "voice", "request_id": 21, "intent": "conversation", "action": {"text": "hey what's up just testing your local whisper box"}}

{"ts": "2026-05-20T09:43:07.119460+00:00", "event": "action_result", "source": "voice", "request_id": 21, "intent": "conversation", "ok": true, "reply": "I am doing well. I am ready for your next instruction.", "config_changed": false}

{"ts": "2026-05-20T09:43:07.168220+00:00", "event": "assistant_response", "source": "voice", "response": "I am doing well. I am ready for your next instruction.", "request_id": 21}

3.3- passed
3.4- i think it works, but i cannot verify as the voice off widget is very small for the amount of text it has on it, and most things are getting clipped. and the widget is not scrollable or resizable

4.1 everything is already working on SAPI only if i am not wrong. so passed
4.2- passed. the transcription was so shitty it took me around half a dozen times just to get it right. but when it got it right, it passed
4.3- passed
4.4- passed. but i cannot see the output in the widget. it is very small for the amount of text on it
4.5- passed
4.6- cannot determine due to no visibility
4.7- again, i think it worked but cannot verify

5.1- passed
5.2- passed
5.3- redundant, module was a transcription error, nevertheless, passed.
5.4- passed. getting tired of the one hardcoded 
5.5- the stt kept on continuing but the wdiget collapsed, it should be on for at least as long as the voice output is continuing. also, the voice outpput is just reading everything from a log with timestamps, not a semantic sumary
5.6- passed. same as 5.5
5.7- failed. "I understood that as a browser request, but I couldn't map the action yet."
5.8- passed. turned off wifi, worked okay
5.9- passed

6.1- passed
6.2- passed
6.3- passed
6.4- passed (searched youtube for "more findings" instead of "lofi beats", but again a transcription issue)
6.5- passed
6.6- passed

7.1- failed. error: audio pipeline failed. audiodevice object has no attribute activate (please check the logs for this)
7.2- failed. transcription erroneously wrong and the same audio pipeline issue. transcription talking about starting surgery
7.3- passed. mute/unmute both works
7.4- passed. transcription issues tho
7.5- failed. first had to switch to text due to shitty transcription, and then the assistant returned opening notepad but did nothing
7.6- passed
7.7- failed.
[main] user text (voice): Pause Media
[main] assistant response: Opening Jellyfin.

8.1- works sometimes, sometimes doesn/t (interprests "whoamii" as "who am i")
8.2- passed. 
8.3- partial pass ([main] assistant response: The command on mac failed: SSH to mac failed: Authentication failed.)
8.4- passsed
8.5- cannot verify because of the panel issues mentioned earlier

 9.1- works, but voice first went offline then text confirmation and not voice confirmation
 9.2- passed
 9.3- passed
 9.4- passed
 9.5- passed
 9.6- works 
 
 10.1- passed
 10.2- passsed
 10.3- passed
 10.4- cannot verify due to issues with widget already mentioned 
10,5- not sure how to replicate or do this test
10.6- passed

11.1- passed

12.1- passed
12.2- auth error, need to configure keyfile 
12.3- alreqdy talked about this

13.1- passed
13.2- passed
13.3- passed
13.4- passed
13.5- passed

14.1- it feels okayish, not that great tbh. it is a neat little project, nothing more
14.2- text is visible but sentences and all cannot be read
14.3- not really
14.4- cannot be read
14.5- not very confusing stuff, other  than the errors 
14.6- no not really, other than when it had errors, 
14.7- there was something about doing surgery, go knows how it go that
14.8- from what i could see in the state docs, the open loops were just compunding, did not seem to get in the way, but they were just getting added to a list or something


NOTES:
even when the widget has been collapsed into an orb, if i click on it a panel should open showing me everything about the widget and service health. 
the widget window should be resizable
1.6- the widget should remeber where it was but at startup also check what is the visible screen and if the location in memory is outside the visible display it should just get to it's default position

also (writing this at the very end of completing the test, set up remote transcription on the mac, to use whisper.cpp with turbo model. so transcription is very fast and more accurate now )

POST-FIX NOTES:
- the voice pipeline now keeps APRIL in speaking state until TTS actually finishes, so the widget should not collapse early anymore
- the widget panel now defaults larger, has a scrollable timeline, and includes a resize grip
- remote shell can now use configured SSH key files
- `say` TTS can route over SSH to the Mac when selected
- the example-based semantic router is now active for local intents, and learned semantic records are persisted for future reuse
- the original test observations above remain useful as a baseline, but several of the major UI and routing blockers have now been repaired
